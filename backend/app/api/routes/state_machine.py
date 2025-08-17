"""
State machine API routes for managing automation rules and fallback configuration.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import CurrentUser, SessionDep
from app.crud.state_machine import (
    create_state_machine_row,
    delete_state_machine_row,
    get_state_machine_fallback,
    get_state_machine_row,
    list_state_machine_rows,
    set_state_machine_fallback,
    update_state_machine_row,
)
from app.models.state_machine import (
    StateMachineFallbackPublic,
    StateMachineFallbackUpdate,
    StateMachineRowCreate,
    StateMachineRowPublic,
    StateMachineRowsPaginated,
    StateMachineRowUpdate,
)
from app.utils_paging import PaginationParams

router = APIRouter()
fallback_router = APIRouter()


@router.get("/", response_model=StateMachineRowsPaginated)
def list_state_machine_rows_endpoint(
    session: SessionDep,
    user: CurrentUser,
    pagination: PaginationParams = Depends(),
    greenhouse_id: uuid.UUID | None = Query(
        None, description="Filter by greenhouse ID"
    ),
) -> StateMachineRowsPaginated:
    """List state machine rows with optional filtering."""
    return list_state_machine_rows(
        session=session,
        user_id=user.id,
        pagination=pagination,
        greenhouse_id=greenhouse_id,
    )


@router.post("/", response_model=StateMachineRowPublic, status_code=201)
def create_state_machine_row_endpoint(
    *,
    session: SessionDep,
    user: CurrentUser,
    row_data: StateMachineRowCreate,
) -> StateMachineRowPublic:
    """Create a new state machine row."""
    try:
        row_dict = create_state_machine_row(
            session=session,
            user_id=user.id,
            row_data=row_data,
        )
        return StateMachineRowPublic(**row_dict)
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{id}", response_model=StateMachineRowPublic)
def get_state_machine_row_endpoint(
    *,
    session: SessionDep,
    user: CurrentUser,
    id: uuid.UUID,
) -> StateMachineRowPublic:
    """Get a state machine row by ID."""
    try:
        row_dict = get_state_machine_row(session=session, user_id=user.id, row_id=id)
        return StateMachineRowPublic(**row_dict)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{id}", response_model=StateMachineRowPublic)
def update_state_machine_row_endpoint(
    *,
    session: SessionDep,
    user: CurrentUser,
    id: uuid.UUID,
    row_data: StateMachineRowUpdate,
) -> StateMachineRowPublic:
    """Update a state machine row."""
    try:
        row_dict = update_state_machine_row(
            session=session,
            user_id=user.id,
            row_id=id,
            row_update=row_data,
        )
        return StateMachineRowPublic(**row_dict)
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        elif "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{id}", status_code=204)
def delete_state_machine_row_endpoint(
    *,
    session: SessionDep,
    user: CurrentUser,
    id: uuid.UUID,
) -> None:
    """Delete a state machine row."""
    try:
        delete_state_machine_row(session=session, user_id=user.id, row_id=id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@fallback_router.get("/{greenhouse_id}", response_model=StateMachineFallbackPublic)
def get_state_machine_fallback_endpoint(
    *,
    session: SessionDep,
    user: CurrentUser,
    greenhouse_id: uuid.UUID,
) -> StateMachineFallbackPublic:
    """Get state machine fallback configuration for a greenhouse."""
    try:
        fallback_dict = get_state_machine_fallback(
            session=session, user_id=user.id, greenhouse_id=greenhouse_id
        )
        if fallback_dict is None:
            raise HTTPException(
                status_code=404, detail="Fallback configuration not found"
            )
        return StateMachineFallbackPublic(**fallback_dict)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@fallback_router.put("/{greenhouse_id}", response_model=StateMachineFallbackPublic)
def set_state_machine_fallback_endpoint(
    *,
    session: SessionDep,
    user: CurrentUser,
    greenhouse_id: uuid.UUID,
    fallback_data: StateMachineFallbackUpdate,
) -> StateMachineFallbackPublic:
    """Set state machine fallback configuration for a greenhouse."""
    try:
        fallback_dict = set_state_machine_fallback(
            session=session,
            user_id=user.id,
            greenhouse_id=greenhouse_id,
            fallback_update=fallback_data,
        )
        return StateMachineFallbackPublic(**fallback_dict)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
