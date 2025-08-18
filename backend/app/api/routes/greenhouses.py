import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.api.permissions import (
    require_owner_permission,
    user_can_access_greenhouse,
)
from app.crud.greenhouses import (
    accept_greenhouse_invite,
    create_greenhouse_invite,
    create_greenhouse_member,
    get_greenhouse_members,
    get_invite_by_token,
    get_user_pending_invites,
)
from app.crud.greenhouses import (
    get_greenhouse as crud_get_greenhouse,
)
from app.crud.greenhouses import (
    remove_greenhouse_member as crud_remove_greenhouse_member,
)
from app.crud.sensors import (
    list_sensors_by_greenhouse,
    list_unmapped_sensors_by_greenhouse,
)
from app.debug_verify import verify_cleanup
from app.models import (
    Greenhouse,
    GreenhouseCreate,
    GreenhouseInvite,
    GreenhouseInvitePublic,
    GreenhouseMember,
    GreenhouseMemberCreate,
    GreenhouseMemberPublic,
    GreenhouseMemberUser,
    GreenhousePublicAPI,
    GreenhousesPaginated,
    GreenhouseUpdate,
    SensorPublic,
    User,
)
from app.models.enums import InviteStatus
from app.utils_paging import Paginated, PaginationParams, paginate_query

router = APIRouter()


# Create pagination dependency
def get_pagination_params(page: int = 1, page_size: int = 50) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]


@router.get("/", response_model=GreenhousesPaginated)
def read_greenhouses(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    pagination: PaginationDep,
) -> GreenhousesPaginated:
    """List greenhouses with pagination using RBAC."""
    # Build base query with user scoping - include shared greenhouses
    from app.api.permissions import ownership_or_membership_condition

    stmt = select(Greenhouse)
    if not current_user.is_superuser:
        stmt = stmt.where(ownership_or_membership_condition(current_user.id))

    # Use the pagination utility and convert to PublicAPI DTOs
    result = paginate_query(session, stmt, pagination)

    # Convert each greenhouse to GreenhousePublicAPI format
    api_greenhouses = [GreenhousePublicAPI.model_validate(gh) for gh in result.data]

    return GreenhousesPaginated(
        data=api_greenhouses,
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/{greenhouse_id}", response_model=GreenhousePublicAPI)
def read_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_id: uuid.UUID,
) -> GreenhousePublicAPI:
    """Get a specific greenhouse by ID."""
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found"
        )
    if not (
        current_user.is_superuser
        or user_can_access_greenhouse(session, greenhouse_id, current_user.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    return GreenhousePublicAPI.model_validate(gh)


@router.post(
    "/", response_model=GreenhousePublicAPI, status_code=status.HTTP_201_CREATED
)
def create_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_in: GreenhouseCreate,
) -> GreenhousePublicAPI:
    """Create a new greenhouse."""
    gh = Greenhouse(**greenhouse_in.model_dump(), user_id=current_user.id)
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return GreenhousePublicAPI.model_validate(gh)


@router.patch("/{greenhouse_id}", response_model=GreenhousePublicAPI)
def update_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_id: uuid.UUID,
    greenhouse_in: GreenhouseUpdate,
) -> GreenhousePublicAPI:
    """Update a greenhouse."""
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found"
        )
    if not (current_user.is_superuser or gh.user_id == current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    updates = greenhouse_in.model_dump(exclude_unset=True)
    gh.sqlmodel_update(updates)
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return GreenhousePublicAPI.model_validate(gh)


@router.delete("/{greenhouse_id}", status_code=204)
def delete_greenhouse(
    *, greenhouse_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
):
    """Delete a greenhouse."""
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or gh.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    session.delete(gh)
    session.commit()

    # Verify cleanup
    print(verify_cleanup(session, gh.id))


@router.get("/{greenhouse_id}/listsensors", response_model=list[SensorPublic])
def list_greenhouse_sensors(
    greenhouse_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
):
    """List all sensors for a specific greenhouse."""
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")

    if not (
        current_user.is_superuser
        or user_can_access_greenhouse(session, greenhouse_id, current_user.id)
    ):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return list_sensors_by_greenhouse(session, greenhouse_id)


@router.get("/{greenhouse_id}/unmapped-sensors", response_model=list[SensorPublic])
def list_unmapped_greenhouse_sensors(
    greenhouse_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
):
    """List all unmapped sensors for a specific greenhouse."""
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")

    # Use RBAC access check
    if not (
        current_user.is_superuser
        or user_can_access_greenhouse(session, greenhouse_id, current_user.id)
    ):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return list_unmapped_sensors_by_greenhouse(session, greenhouse_id)


# -------------------------------------------------------
# RBAC SHARING ENDPOINTS
# -------------------------------------------------------


@router.get(
    "/{greenhouse_id}/members", response_model=Paginated[GreenhouseMemberPublic]
)
def get_greenhouse_members_endpoint(
    greenhouse_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    pagination: PaginationDep,
):
    """Get members of a greenhouse (owner only)."""
    # Verify greenhouse exists and user is owner
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")

    require_owner_permission(session, greenhouse_id, current_user.id)

    # Get members with pagination
    members_and_users = get_greenhouse_members(
        session, greenhouse_id, skip=pagination.skip, limit=pagination.page_size
    )

    # Convert to public format
    members_public = []
    for member, user in members_and_users:
        user_data = GreenhouseMemberUser(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        member_public = GreenhouseMemberPublic(
            user=user_data, role=member.role, added_at=member.created_at
        )
        members_public.append(member_public)

    # Get proper total count
    from sqlmodel import func

    total_count = session.exec(
        select(func.count())
        .select_from(GreenhouseMember)
        .where(GreenhouseMember.greenhouse_id == greenhouse_id)
    ).one()

    return Paginated[GreenhouseMemberPublic](
        data=members_public,
        page=pagination.page,
        page_size=pagination.page_size,
        total=total_count,
    )


@router.post("/{greenhouse_id}/members", status_code=201)
def add_greenhouse_member(
    greenhouse_id: uuid.UUID,
    member_data: GreenhouseMemberCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Add a member to greenhouse or create invitation (owner only)."""
    # Verify greenhouse exists and user is owner
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")

    require_owner_permission(session, greenhouse_id, current_user.id)

    # Check if user exists
    from sqlmodel import select

    user = session.exec(select(User).where(User.email == member_data.email)).first()

    if user:
        # User exists - create direct membership
        try:
            member = create_greenhouse_member(
                session, greenhouse_id, user.id, member_data.role
            )
            return {
                "type": "member",
                "member": GreenhouseMemberPublic(
                    user=GreenhouseMemberUser(
                        id=user.id,
                        email=user.email,
                        full_name=user.full_name,
                        is_active=user.is_active,
                        created_at=user.created_at,
                        updated_at=user.updated_at,
                    ),
                    role=member.role,
                    added_at=member.created_at,
                ),
            }
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=409, detail="User is already a member")
        except Exception:
            session.rollback()
            raise HTTPException(status_code=400, detail="Failed to add member")
    else:
        # User doesn't exist - check for existing pending invite first
        from datetime import datetime, timezone

        existing = session.exec(
            select(GreenhouseInvite).where(
                GreenhouseInvite.greenhouse_id == greenhouse_id,
                GreenhouseInvite.email == member_data.email,
                GreenhouseInvite.status == InviteStatus.PENDING,
                GreenhouseInvite.expires_at > datetime.now(timezone.utc),
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=409, detail="Pending invitation already exists"
            )

        # Create invitation
        try:
            invite = create_greenhouse_invite(
                session,
                greenhouse_id,
                member_data.email,
                member_data.role,
                current_user.id,
            )
            return {
                "type": "invite",
                "invite": GreenhouseInvitePublic.model_validate(invite),
            }
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=409, detail="Invitation already exists for this email"
            )
        except Exception:
            session.rollback()
            raise HTTPException(status_code=400, detail="Failed to create invitation")


@router.delete("/{greenhouse_id}/members/{user_id}", status_code=204)
def remove_greenhouse_member(
    greenhouse_id: uuid.UUID,
    user_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Remove a member from greenhouse (owner only)."""
    # Verify greenhouse exists and user is owner
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")

    require_owner_permission(session, greenhouse_id, current_user.id)

    # Cannot remove the owner
    if user_id == greenhouse.user_id:
        raise HTTPException(status_code=400, detail="Cannot remove greenhouse owner")

    # Remove member
    removed = crud_remove_greenhouse_member(session, greenhouse_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")


@router.post("/{greenhouse_id}/leave", status_code=204)
def leave_greenhouse(
    greenhouse_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Leave a shared greenhouse (operator only - owners cannot leave)."""
    # Verify greenhouse exists
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")

    # Owners cannot leave their own greenhouse
    if greenhouse.user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Greenhouse owners cannot leave their own greenhouse",
        )

    # Remove membership
    removed = crud_remove_greenhouse_member(session, greenhouse_id, current_user.id)
    if not removed:
        raise HTTPException(
            status_code=404, detail="You are not a member of this greenhouse"
        )


# -------------------------------------------------------
# INVITATION ENDPOINTS
# -------------------------------------------------------


@router.get("/invites/me", response_model=list[GreenhouseInvitePublic])
def get_my_invitations(
    session: SessionDep,
    current_user: CurrentUser,
):
    """Get pending invitations for current user."""
    invites = get_user_pending_invites(session, current_user.email)
    return [GreenhouseInvitePublic.model_validate(invite) for invite in invites]


@router.post("/invites/{token}/accept", status_code=201)
def accept_invitation(
    token: str,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Accept a greenhouse invitation."""
    # Get invitation
    invite = get_invite_by_token(session, token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found")

    # Check if invitation is valid
    if invite.status != InviteStatus.PENDING:
        raise HTTPException(status_code=400, detail="Invitation is no longer valid")

    from datetime import datetime, timezone

    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation has expired")

    # Check if email matches
    if invite.email != current_user.email:
        raise HTTPException(
            status_code=403, detail="This invitation is not for your email address"
        )

    # Accept invitation
    try:
        member = accept_greenhouse_invite(session, invite, current_user.id)
        return {
            "message": "Invitation accepted successfully",
            "member": GreenhouseMemberPublic(
                user=GreenhouseMemberUser(
                    id=current_user.id,
                    email=current_user.email,
                    full_name=current_user.full_name,
                    is_active=current_user.is_active,
                    created_at=current_user.created_at,
                    updated_at=current_user.updated_at,
                ),
                role=member.role,
                added_at=member.created_at,
            ),
        }
    except Exception as e:
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=409, detail="You are already a member of this greenhouse"
            )
        raise HTTPException(status_code=400, detail="Failed to accept invitation")
