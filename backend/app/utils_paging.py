"""
Pagination utilities for converting page/page_size to offset/limit
and providing standardized paginated response models.

Follows the API spec requirements:
- Accept page and page_size query parameters
- Return {data, page, page_size, total} response format
- Default page_size = 50, max = 200
- Normalize negative/zero values to defaults
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Select
from sqlmodel import Session, func, select

# Generic type for paginated data
T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for pagination with validation and normalization."""

    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(
        default=50, ge=1, le=200, description="Number of items per page (max 200)"
    )

    @field_validator("page", mode="before")
    @classmethod
    def normalize_page(cls, v) -> int:
        """Normalize page to at least 1."""
        if v is None or v < 1:
            return 1
        return v

    @field_validator("page_size", mode="before")
    @classmethod
    def normalize_page_size(cls, v) -> int:
        """Normalize page_size to default 50 if invalid, max 200."""
        if v is None or v < 1:
            return 50
        if v > 200:
            return 200
        return v


class Paginated(BaseModel, Generic[T]):
    """
    Generic paginated response wrapper.

    Provides consistent pagination format across all list endpoints:
    {data, page, page_size, total}
    """

    data: list[T] = Field(description="Array of items for this page")
    page: int = Field(description="Current page number (1-based)")
    page_size: int = Field(description="Number of items per page")
    total: int = Field(description="Total number of items across all pages")


def page_to_offset(page: int, page_size: int) -> tuple[int, int]:
    """
    Convert page/page_size parameters to offset/limit for database queries.

    Args:
        page: Page number (1-based)
        page_size: Items per page

    Returns:
        Tuple of (offset, limit) for use with SQLModel .offset() and .limit()

    Examples:
        >>> page_to_offset(1, 50)
        (0, 50)
        >>> page_to_offset(3, 25)
        (50, 25)
    """
    # Ensure minimum values
    page = max(1, page)
    page_size = max(1, min(200, page_size))

    offset = (page - 1) * page_size
    limit = page_size

    return offset, limit


def paginate_query(
    session: Session, statement: Select, pagination: PaginationParams
) -> Paginated[T]:
    """
    Execute a paginated query and return standardized Paginated response.

    Args:
        session: SQLModel database session
        statement: Base SELECT statement to paginate
        pagination: Pagination parameters

    Returns:
        Paginated response with data, page, page_size, and total

    Example:
        ```python
        from app.utils_paging import paginate_query, PaginationParams
        from app.models import Greenhouse

        # In your route handler:
        pagination = PaginationParams(page=page, page_size=page_size)
        base_query = select(Greenhouse).where(Greenhouse.owner_id == user.id)
        result = paginate_query(session, base_query, pagination)
        return result
        ```
    """
    # Get total count
    count_statement = select(func.count()).select_from(statement.subquery())
    total = session.exec(count_statement).one()

    # Apply pagination to the main query
    offset, limit = page_to_offset(pagination.page, pagination.page_size)
    paginated_statement = statement.offset(offset).limit(limit)

    # Execute and get results
    results = session.exec(paginated_statement).all()

    return Paginated(
        data=results, page=pagination.page, page_size=pagination.page_size, total=total
    )


def create_pagination_dependency():
    """
    Create a FastAPI dependency for pagination parameters.

    Returns:
        Function that can be used as a FastAPI dependency to extract
        page and page_size from query parameters.

    Example:
        ```python
        from fastapi import Depends
        from app.utils_paging import create_pagination_dependency

        PaginationDep = Annotated[PaginationParams, Depends(create_pagination_dependency())]

        @router.get("/items", response_model=Paginated[ItemPublic])
        def list_items(pagination: PaginationDep) -> Paginated[ItemPublic]:
            # pagination.page and pagination.page_size are already validated
            pass
        ```
    """

    def get_pagination_params(page: int = 1, page_size: int = 50) -> PaginationParams:
        return PaginationParams(page=page, page_size=page_size)

    return get_pagination_params
