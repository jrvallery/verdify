"""
CRUD operations for state machine rows and fallback configuration.
"""

import uuid
from typing import Any

from sqlmodel import Session, select

from app.crud.greenhouses import validate_user_owns_greenhouse
from app.models import (
    Greenhouse,
    StateMachineFallback,
    StateMachineFallbackUpdate,
    StateMachineRow,
    StateMachineRowCreate,
    StateMachineRowsPaginated,
    StateMachineRowUpdate,
)
from app.utils_paging import PaginationParams, paginate_query


def _convert_uuid_lists_to_strings(data: dict) -> dict:
    """Convert UUID lists to string lists for JSON storage."""
    converted = data.copy()
    for field in ["must_on_actuators", "must_off_actuators"]:
        if field in converted and converted[field] is not None:
            converted[field] = [
                str(uuid_obj) if isinstance(uuid_obj, uuid.UUID) else uuid_obj
                for uuid_obj in converted[field]
            ]
    return converted


def _convert_uuid_lists_from_strings(row: StateMachineRow) -> StateMachineRow:
    """Convert string lists back to UUID lists when returning data."""
    # Convert the stored string UUIDs back to UUID objects for API response
    if row.must_on_actuators:
        row.must_on_actuators = [
            uuid.UUID(uuid_str) if isinstance(uuid_str, str) else uuid_str
            for uuid_str in row.must_on_actuators
        ]
    if row.must_off_actuators:
        row.must_off_actuators = [
            uuid.UUID(uuid_str) if isinstance(uuid_str, str) else uuid_str
            for uuid_str in row.must_off_actuators
        ]
    return row


# ================================================================
# STATE MACHINE ROW CRUD
# ================================================================


def validate_user_owns_state_machine_row(
    session: Session, user_id: uuid.UUID, row_id: uuid.UUID
) -> StateMachineRow:
    """Validate that user owns the state machine row and return it."""
    query = (
        select(StateMachineRow)
        .join(Greenhouse)
        .where(StateMachineRow.id == row_id, Greenhouse.user_id == user_id)
    )
    row = session.exec(query).first()
    if not row:
        raise ValueError(f"State machine row {row_id} not found or access denied")
    return row


def list_state_machine_rows(
    session: Session,
    user_id: uuid.UUID,
    pagination: PaginationParams,
    greenhouse_id: uuid.UUID | None = None,
) -> StateMachineRowsPaginated:
    """List state machine rows with filtering and pagination."""
    # Base query - join with greenhouse for ownership validation
    query = (
        select(StateMachineRow).join(Greenhouse).where(Greenhouse.user_id == user_id)
    )

    # Apply greenhouse filter if provided
    if greenhouse_id:
        query = query.where(StateMachineRow.greenhouse_id == greenhouse_id)

    # Order by fallback status, then temp_stage, then humi_stage
    query = query.order_by(
        StateMachineRow.is_fallback,
        StateMachineRow.temp_stage.nulls_last(),
        StateMachineRow.humi_stage.nulls_last(),
    )

    # Apply pagination and return
    return paginate_query(session, query, pagination)


def get_state_machine_row(
    session: Session, user_id: uuid.UUID, row_id: uuid.UUID
) -> dict[str, Any]:
    """Get a state machine row by ID."""
    row = validate_user_owns_state_machine_row(session, user_id, row_id)

    # Return dict with UUID conversion for API response
    return {
        "id": row.id,
        "greenhouse_id": row.greenhouse_id,
        "temp_stage": row.temp_stage,
        "humi_stage": row.humi_stage,
        "is_fallback": row.is_fallback,
        "must_on_actuators": [
            uuid.UUID(uuid_str) for uuid_str in row.must_on_actuators
        ],
        "must_off_actuators": [
            uuid.UUID(uuid_str) for uuid_str in row.must_off_actuators
        ],
        "must_on_fan_groups": row.must_on_fan_groups,
        "created_at": row.created_at,
    }


def create_state_machine_row(
    session: Session, user_id: uuid.UUID, row_data: StateMachineRowCreate
) -> dict[str, Any]:
    """Create a new state machine row."""
    # Validate user owns the greenhouse
    validate_user_owns_greenhouse(session, row_data.greenhouse_id, user_id)

    # Check for duplicate grid position (except for fallback rows)
    if not row_data.is_fallback:
        existing = session.exec(
            select(StateMachineRow).where(
                StateMachineRow.greenhouse_id == row_data.greenhouse_id,
                StateMachineRow.temp_stage == row_data.temp_stage,
                StateMachineRow.humi_stage == row_data.humi_stage,
                StateMachineRow.is_fallback == False,
            )
        ).first()
        if existing:
            raise ValueError(
                "State machine row with this temp_stage/humi_stage already exists"
            )

    # Create the row with manual conversion to avoid JSON serialization issues
    row = StateMachineRow(
        greenhouse_id=row_data.greenhouse_id,
        temp_stage=row_data.temp_stage,
        humi_stage=row_data.humi_stage,
        is_fallback=row_data.is_fallback,
        must_on_actuators=[str(uuid_obj) for uuid_obj in row_data.must_on_actuators],
        must_off_actuators=[str(uuid_obj) for uuid_obj in row_data.must_off_actuators],
        must_on_fan_groups=row_data.must_on_fan_groups,
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    # Return a dict that can be used to create StateMachineRowPublic
    return {
        "id": row.id,
        "greenhouse_id": row.greenhouse_id,
        "temp_stage": row.temp_stage,
        "humi_stage": row.humi_stage,
        "is_fallback": row.is_fallback,
        "must_on_actuators": [
            uuid.UUID(uuid_str) for uuid_str in row.must_on_actuators
        ],
        "must_off_actuators": [
            uuid.UUID(uuid_str) for uuid_str in row.must_off_actuators
        ],
        "must_on_fan_groups": row.must_on_fan_groups,
        "created_at": row.created_at,
    }


def update_state_machine_row(
    session: Session,
    user_id: uuid.UUID,
    row_id: uuid.UUID,
    row_update: StateMachineRowUpdate,
) -> dict[str, Any]:
    """Update a state machine row."""
    row = validate_user_owns_state_machine_row(session, user_id, row_id)

    # Check for duplicate grid position if temp/humi stages are being updated
    update_data = row_update.model_dump(exclude_unset=True)
    if not row.is_fallback and (
        "temp_stage" in update_data or "humi_stage" in update_data
    ):
        new_temp_stage = update_data.get("temp_stage", row.temp_stage)
        new_humi_stage = update_data.get("humi_stage", row.humi_stage)

        existing = session.exec(
            select(StateMachineRow).where(
                StateMachineRow.greenhouse_id == row.greenhouse_id,
                StateMachineRow.temp_stage == new_temp_stage,
                StateMachineRow.humi_stage == new_humi_stage,
                StateMachineRow.is_fallback == False,
                StateMachineRow.id != row_id,  # Exclude current row
            )
        ).first()
        if existing:
            raise ValueError(
                "State machine row with this temp_stage/humi_stage already exists"
            )

    # Convert UUID lists to strings for storage
    converted_data = update_data.copy()
    for field in ["must_on_actuators", "must_off_actuators"]:
        if field in converted_data and converted_data[field] is not None:
            converted_data[field] = [
                str(uuid_obj) for uuid_obj in converted_data[field]
            ]

    # Update fields
    for field, value in converted_data.items():
        setattr(row, field, value)

    session.add(row)
    session.commit()
    session.refresh(row)

    # Return a dict with UUID conversion for API response
    return {
        "id": row.id,
        "greenhouse_id": row.greenhouse_id,
        "temp_stage": row.temp_stage,
        "humi_stage": row.humi_stage,
        "is_fallback": row.is_fallback,
        "must_on_actuators": [
            uuid.UUID(uuid_str) for uuid_str in row.must_on_actuators
        ],
        "must_off_actuators": [
            uuid.UUID(uuid_str) for uuid_str in row.must_off_actuators
        ],
        "must_on_fan_groups": row.must_on_fan_groups,
        "created_at": row.created_at,
    }


def delete_state_machine_row(
    session: Session, user_id: uuid.UUID, row_id: uuid.UUID
) -> None:
    """Delete a state machine row."""
    row = validate_user_owns_state_machine_row(session, user_id, row_id)
    session.delete(row)
    session.commit()


# ================================================================
# STATE MACHINE FALLBACK CRUD
# ================================================================


def get_state_machine_fallback(
    session: Session, user_id: uuid.UUID, greenhouse_id: uuid.UUID
) -> dict[str, Any] | None:
    """Get state machine fallback for a greenhouse."""
    # Validate user owns the greenhouse
    validate_user_owns_greenhouse(session, greenhouse_id, user_id)

    query = select(StateMachineFallback).where(
        StateMachineFallback.greenhouse_id == greenhouse_id
    )
    fallback = session.exec(query).first()

    if fallback:
        return {
            "greenhouse_id": fallback.greenhouse_id,
            "must_on_actuators": [
                uuid.UUID(uuid_str) for uuid_str in fallback.must_on_actuators
            ],
            "must_off_actuators": [
                uuid.UUID(uuid_str) for uuid_str in fallback.must_off_actuators
            ],
            "must_on_fan_groups": fallback.must_on_fan_groups,
        }
    return None


def set_state_machine_fallback(
    session: Session,
    user_id: uuid.UUID,
    greenhouse_id: uuid.UUID,
    fallback_update: StateMachineFallbackUpdate,
) -> dict[str, Any]:
    """Set/update state machine fallback for a greenhouse."""
    # Validate user owns the greenhouse
    validate_user_owns_greenhouse(session, greenhouse_id, user_id)

    # Check if fallback already exists
    existing = session.exec(
        select(StateMachineFallback).where(
            StateMachineFallback.greenhouse_id == greenhouse_id
        )
    ).first()

    if existing:
        # Update existing fallback
        update_data = fallback_update.model_dump(exclude_unset=True)
        # Convert UUID lists to strings for storage
        converted_data = update_data.copy()
        for field in ["must_on_actuators", "must_off_actuators"]:
            if field in converted_data and converted_data[field] is not None:
                converted_data[field] = [
                    str(uuid_obj) for uuid_obj in converted_data[field]
                ]

        for field, value in converted_data.items():
            setattr(existing, field, value)

        session.add(existing)
        session.commit()
        session.refresh(existing)

        # Return dict with UUID conversion
        return {
            "greenhouse_id": existing.greenhouse_id,
            "must_on_actuators": [
                uuid.UUID(uuid_str) for uuid_str in existing.must_on_actuators
            ],
            "must_off_actuators": [
                uuid.UUID(uuid_str) for uuid_str in existing.must_off_actuators
            ],
            "must_on_fan_groups": existing.must_on_fan_groups,
        }
    else:
        # Create new fallback
        fallback_data = fallback_update.model_dump(exclude_unset=True)
        fallback_data["greenhouse_id"] = greenhouse_id

        # Convert UUID lists to strings for storage
        for field in ["must_on_actuators", "must_off_actuators"]:
            if field in fallback_data and fallback_data[field] is not None:
                fallback_data[field] = [
                    str(uuid_obj) for uuid_obj in fallback_data[field]
                ]

        fallback = StateMachineFallback(**fallback_data)
        session.add(fallback)
        session.commit()
        session.refresh(fallback)

        # Return dict with UUID conversion
        return {
            "greenhouse_id": fallback.greenhouse_id,
            "must_on_actuators": [
                uuid.UUID(uuid_str) for uuid_str in fallback.must_on_actuators
            ],
            "must_off_actuators": [
                uuid.UUID(uuid_str) for uuid_str in fallback.must_off_actuators
            ],
            "must_on_fan_groups": fallback.must_on_fan_groups,
        }
