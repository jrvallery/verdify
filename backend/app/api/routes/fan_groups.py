import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.crud.controller import get_controller as crud_get_controller
from app.crud.fan_groups import (
    add_fan_group_member,
    list_fan_groups,
    remove_fan_group_member,
    validate_user_owns_fan_group,
)
from app.crud.fan_groups import (
    create_fan_group as crud_create_fan_group,
)
from app.crud.fan_groups import (
    delete_fan_group as crud_delete_fan_group,
)
from app.crud.fan_groups import (
    get_fan_group as crud_get_fan_group,
)
from app.crud.fan_groups import (
    update_fan_group as crud_update_fan_group,
)
from app.models import (
    FanGroupCreate,
    FanGroupMemberCreate,
    FanGroupMemberPublic,
    FanGroupPublic,
    FanGroupsPaginated,
    FanGroupUpdate,
)
from app.utils_paging import PaginationParams

router = APIRouter()


@router.get("/", response_model=FanGroupsPaginated)
def list_fan_groups_endpoint(
    session: SessionDep,
    current_user: CurrentUser,
    controller_id: uuid.UUID | None = Query(
        None, description="Filter by controller ID"
    ),
    sort: str = Query("name", description="Sort field and direction"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
) -> FanGroupsPaginated:
    """List fan groups with optional filtering."""
    pagination = PaginationParams(page=page, page_size=page_size)
    return list_fan_groups(
        session=session,
        user_id=current_user.id,
        pagination=pagination,
        controller_id=controller_id,
        sort=sort,
    )


@router.post("/", response_model=FanGroupPublic, status_code=status.HTTP_201_CREATED)
def create_fan_group_endpoint(
    fan_group_in: FanGroupCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> FanGroupPublic:
    """Create a new fan group."""
    # Validate that user owns the controller
    controller = crud_get_controller(session, fan_group_in.controller_id)
    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Controller not found"
        )

    # Check ownership through greenhouse
    from app.crud.greenhouses import validate_user_owns_greenhouse

    if not validate_user_owns_greenhouse(
        session, controller.greenhouse_id, current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    try:
        fan_group = crud_create_fan_group(session, fan_group_in)
        return FanGroupPublic.model_validate(fan_group)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{fan_group_id}", response_model=FanGroupPublic)
def get_fan_group_endpoint(
    fan_group_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> FanGroupPublic:
    """Get a fan group by ID."""
    fan_group = crud_get_fan_group(session, fan_group_id)
    if not fan_group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fan group not found"
        )

    # Validate ownership
    if not validate_user_owns_fan_group(session, fan_group_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    return FanGroupPublic.model_validate(fan_group)


@router.patch("/{fan_group_id}", response_model=FanGroupPublic)
def update_fan_group_endpoint(
    fan_group_id: uuid.UUID,
    fan_group_in: FanGroupUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> FanGroupPublic:
    """Update a fan group."""
    # Validate ownership first
    if not validate_user_owns_fan_group(session, fan_group_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    fan_group = crud_update_fan_group(session, fan_group_id, fan_group_in)
    if not fan_group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fan group not found"
        )

    return FanGroupPublic.model_validate(fan_group)


@router.delete("/{fan_group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fan_group_endpoint(
    fan_group_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    """Delete a fan group."""
    # Validate ownership first
    if not validate_user_owns_fan_group(session, fan_group_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    if not crud_delete_fan_group(session, fan_group_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fan group not found"
        )


@router.post(
    "/{fan_group_id}/members",
    response_model=FanGroupMemberPublic,
    status_code=status.HTTP_201_CREATED,
)
def add_fan_group_member_endpoint(
    fan_group_id: uuid.UUID,
    member_in: FanGroupMemberCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> FanGroupMemberPublic:
    """Add an actuator to a fan group."""
    # Validate ownership first
    if not validate_user_owns_fan_group(session, fan_group_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    try:
        member = add_fan_group_member(session, fan_group_id, member_in.actuator_id)
        return FanGroupMemberPublic(
            fan_group_id=member.fan_group_id, actuator_id=member.actuator_id
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.delete("/{fan_group_id}/members", status_code=status.HTTP_204_NO_CONTENT)
def remove_fan_group_member_endpoint(
    fan_group_id: uuid.UUID,
    actuator_id: uuid.UUID = Query(..., description="Actuator ID to remove"),
    session: SessionDep = ...,
    current_user: CurrentUser = ...,
) -> None:
    """Remove an actuator from a fan group."""
    # Validate ownership first
    if not validate_user_owns_fan_group(session, fan_group_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    if not remove_fan_group_member(session, fan_group_id, actuator_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fan group member not found"
        )
