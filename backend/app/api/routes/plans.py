"""
Plan management endpoints.

Provides CRUD operations for cultivation plans and device plan fetch endpoints.
Plans define setpoints, irrigation schedules, and other cultivation parameters.
Only one plan can be active per greenhouse at a time.
"""

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlmodel import Session, and_, desc, select

from app.api.deps import (
    CurrentDevice,
    CurrentUser,
    PaginationDep,
    SessionDep,
    get_current_active_superuser,
)
from app.models import (
    Greenhouse,
    Plan,
    PlanCreate,
    PlanPublic,
    PlansPaginated,
)
from app.utils_paging import paginate_query

router = APIRouter()


def generate_plan_etag(payload: dict, version: int) -> str:
    """Generate strong ETag for plan payload."""
    # Create canonical JSON representation
    canonical_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    # Generate SHA-256 hash
    hash_obj = hashlib.sha256(canonical_json.encode("utf-8"))
    sha8 = hash_obj.hexdigest()[:8]

    return f"plan:v{version}:{sha8}"


def get_latest_active_plan(session: Session, greenhouse_id: str) -> Plan | None:
    """Get the latest active plan for a greenhouse."""
    statement = (
        select(Plan)
        .where(and_(Plan.greenhouse_id == greenhouse_id, Plan.is_active is True))
        .order_by(desc(Plan.version))
        .limit(1)
    )
    return session.exec(statement).first()


def get_latest_plan(session: Session, greenhouse_id: str) -> Plan | None:
    """Get the latest plan (active or not) for a greenhouse."""
    statement = (
        select(Plan)
        .where(Plan.greenhouse_id == greenhouse_id)
        .order_by(desc(Plan.version))
        .limit(1)
    )
    return session.exec(statement).first()


def deactivate_existing_plans(session: Session, greenhouse_id: str) -> None:
    """Deactivate all existing active plans for a greenhouse."""
    statement = select(Plan).where(
        and_(Plan.greenhouse_id == greenhouse_id, Plan.is_active is True)
    )
    existing_plans = session.exec(statement).all()

    for plan in existing_plans:
        plan.is_active = False

    session.add_all(existing_plans)


def create_plan_response(
    plan: Plan,
    accept_encoding: str | None = None,
) -> tuple[dict, dict[str, str]]:
    """Create plan response with proper headers and optional gzip compression."""
    payload = plan.payload
    headers = {
        "ETag": f'"{plan.etag}"',
        "Last-Modified": plan.created_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "Cache-Control": "private, must-revalidate",
    }

    # Optional gzip compression (phase-2 feature)
    if accept_encoding and "gzip" in accept_encoding:
        import gzip

        json_content = json.dumps(payload, separators=(",", ":"))
        compressed_content = gzip.compress(json_content.encode("utf-8"))
        headers["Content-Encoding"] = "gzip"
        # Note: FastAPI will handle the actual gzip response automatically

    return payload, headers


# Admin endpoints (UserJWT auth)


@router.get(
    "/plans",
    response_model=PlansPaginated,
    summary="List plan versions",
    description="List plan versions for a greenhouse with pagination and filtering.",
    responses={
        200: {"description": "List of plan versions with pagination"},
        401: {"description": "Unauthorized"},
        404: {"description": "Greenhouse not found"},
    },
    tags=["Plan"],
)
def list_plans(
    session: SessionDep,
    current_user: CurrentUser,
    pagination: PaginationDep,
    greenhouse_id: Annotated[str, Query(..., description="Greenhouse UUID")] = None,
    active: Annotated[
        bool | None, Query(description="Filter to active plan only")
    ] = None,
    sort: Annotated[
        str,
        Query(
            description="Sort field and direction",
            pattern="^(-?)((version)|(created_at))$",
        ),
    ] = "-version",
):
    """
    List plan versions for a greenhouse.

    Args:
        session: Database session
        current_user: Current authenticated user
        pagination: Pagination parameters
        greenhouse_id: Greenhouse UUID to filter plans
        active: Filter to active plans only
        sort: Sort field and direction (version, created_at, -version, -created_at)

    Returns:
        Paginated list of plan versions
    """
    if not greenhouse_id:
        raise HTTPException(
            status_code=400,
            detail="greenhouse_id query parameter is required",
        )

    # Verify greenhouse exists and user has access
    greenhouse = session.get(Greenhouse, greenhouse_id)
    if not greenhouse:
        raise HTTPException(
            status_code=404,
            detail="Greenhouse not found",
        )

    # TODO: Add proper ownership/access control
    # For now, allow any authenticated user to access

    # Build query
    query = select(Plan).where(Plan.greenhouse_id == greenhouse_id)

    # Apply active filter
    if active is not None:
        query = query.where(Plan.is_active == active)

    # Apply sorting
    if sort.startswith("-"):
        field = sort[1:]
        if field == "version":
            query = query.order_by(desc(Plan.version))
        elif field == "created_at":
            query = query.order_by(desc(Plan.created_at))
    else:
        if sort == "version":
            query = query.order_by(Plan.version)
        elif sort == "created_at":
            query = query.order_by(Plan.created_at)

    # Paginate results
    return paginate_query(session, query, pagination)


@router.post(
    "/plans",
    response_model=PlanPublic,
    status_code=201,
    summary="Create new plan version",
    description="Create a new plan version for a greenhouse. Only one plan can be active at a time.",
    responses={
        201: {"description": "Plan created successfully"},
        400: {"description": "Bad request"},
        409: {"description": "Conflict (e.g., version already exists)"},
    },
    tags=["Plan"],
)
def create_plan(
    session: SessionDep,
    plan_create: PlanCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_active_superuser)],
):
    """
    Create a new plan version.

    Restricted to superusers only. In production, plan generation should be
    handled by internal Celery tasks rather than direct API creation.

    Args:
        session: Database session
        plan_create: Plan creation data
        current_user: Current authenticated superuser

    Returns:
        Created plan
    """
    # Verify greenhouse exists and user has access
    greenhouse = session.get(Greenhouse, plan_create.greenhouse_id)
    if not greenhouse:
        raise HTTPException(
            status_code=404,
            detail="Greenhouse not found",
        )

    # TODO: Add proper ownership/access control
    # For now, allow any authenticated user to create plans

    # Get next version number
    latest_plan = get_latest_plan(session, str(plan_create.greenhouse_id))
    next_version = (latest_plan.version + 1) if latest_plan else 1

    # Generate ETag
    etag = generate_plan_etag(plan_create.payload.model_dump(mode="json"), next_version)

    # If this plan should be active, deactivate existing active plans
    if plan_create.is_active:
        deactivate_existing_plans(session, str(plan_create.greenhouse_id))

    # Create new plan
    db_plan = Plan(
        greenhouse_id=plan_create.greenhouse_id,
        version=next_version,
        payload=plan_create.payload.model_dump(
            mode="json"
        ),  # Convert to dict for JSON storage
        etag=etag,
        is_active=plan_create.is_active,
        effective_from=plan_create.effective_from,
        effective_to=plan_create.effective_to,
        created_by=current_user.id,
    )

    session.add(db_plan)
    session.commit()
    session.refresh(db_plan)

    return db_plan


# Device endpoints (DeviceToken auth)


@router.get(
    "/controllers/{controller_id}/plan",
    summary="Controller fetches current plan (ETag supported)",
    description="Fetch plan for controller by controller ID. Uses ETag for caching.",
    responses={
        200: {"description": "Plan payload"},
        304: {"description": "Not modified (ETag match)"},
        401: {"description": "Device token required"},
        404: {"description": "Controller or plan not found"},
    },
    tags=["Plan"],
)
def get_plan_by_controller_id(
    controller_id: str,
    session: SessionDep,
    current_device: CurrentDevice,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    accept_encoding: Annotated[str | None, Header(alias="Accept-Encoding")] = None,
):
    """
    Get plan for a controller by controller ID.

    Args:
        controller_id: Controller UUID
        session: Database session
        current_device: Controller from device token auth
        if_none_match: ETag for conditional requests
        accept_encoding: Accept-Encoding header for optional gzip

    Returns:
        Plan payload with ETag headers or 304 if not modified
    """
    # Verify the device token matches the requested controller
    if str(current_device.id) != controller_id:
        raise HTTPException(
            status_code=403,
            detail="Device token does not match requested controller",
        )

    # Ensure device is associated with a greenhouse
    if not current_device.greenhouse_id:
        raise HTTPException(
            status_code=404,
            detail="Controller not associated with a greenhouse",
        )

    # Get latest active plan for the greenhouse
    plan = get_latest_active_plan(session, str(current_device.greenhouse_id))
    if not plan:
        raise HTTPException(
            status_code=404,
            detail="No active plan found for this greenhouse",
        )

    # Check ETag for conditional requests
    if if_none_match and if_none_match.strip('"') == plan.etag:
        return Response(status_code=304)

    # Create response with proper headers
    payload, headers = create_plan_response(plan, accept_encoding)

    return Response(
        content=json.dumps(payload, separators=(",", ":")),
        media_type="application/json",
        headers=headers,
    )


@router.get(
    "/controllers/me/plan",
    summary="Controller fetches current plan for authenticated device",
    description="Fetch plan for the authenticated controller. Uses ETag for caching.",
    responses={
        200: {"description": "Plan payload"},
        304: {"description": "Not modified (ETag match)"},
        401: {"description": "Device token required"},
        404: {"description": "Plan not found"},
    },
    tags=["Plan"],
)
def get_plan_for_current_device(
    session: SessionDep,
    current_device: CurrentDevice,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    accept_encoding: Annotated[str | None, Header(alias="Accept-Encoding")] = None,
):
    """
    Get plan for the authenticated controller.

    This is a convenience endpoint that allows controllers to fetch their
    plan without needing to specify their controller ID.

    Args:
        session: Database session
        current_device: Controller from device token auth
        if_none_match: ETag for conditional requests
        accept_encoding: Accept-Encoding header for optional gzip

    Returns:
        Plan payload with ETag headers or 304 if not modified
    """
    # Ensure device is associated with a greenhouse
    if not current_device.greenhouse_id:
        raise HTTPException(
            status_code=404,
            detail="Controller not associated with a greenhouse",
        )

    # Get latest active plan for the greenhouse
    plan = get_latest_active_plan(session, str(current_device.greenhouse_id))
    if not plan:
        raise HTTPException(
            status_code=404,
            detail="No active plan found for this greenhouse",
        )

    # Check ETag for conditional requests
    if if_none_match and if_none_match.strip('"') == plan.etag:
        return Response(status_code=304)

    # Create response with proper headers
    payload, headers = create_plan_response(plan, accept_encoding)

    return Response(
        content=json.dumps(payload, separators=(",", ":")),
        media_type="application/json",
        headers=headers,
    )
