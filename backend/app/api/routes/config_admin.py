"""
Config Admin API routes for Project Verdify.

This module provides endpoints for publishing greenhouse configurations,
generating diffs, and managing config snapshots with ETag support.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import get_current_user, get_db
from app.core.config_build import ConfigBuilder
from app.models import (
    ConfigDiff,
    ConfigPublishRequest,
    ConfigPublishResult,
    ConfigSnapshot,
    ConfigSnapshotCreate,
    Greenhouse,
    User,
)

router = APIRouter()


@router.post(
    "/greenhouses/{greenhouse_id}/config/publish",
    response_model=ConfigPublishResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Dry-run preview (no snapshot persisted)"},
        201: {"description": "Published config (new snapshot created)"},
        400: {"description": "Validation errors"},
        404: {"description": "Greenhouse not found"},
        409: {"description": "Configuration conflicts"},
    },
)
def publish_greenhouse_config(
    greenhouse_id: uuid.UUID,
    request: ConfigPublishRequest = ConfigPublishRequest(),
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConfigPublishResult:
    """
    Materialize and publish config snapshot for a greenhouse.

    This endpoint:
    1. Gathers all configuration data from database tables
    2. Validates completeness and constraints
    3. Generates deterministic config payload with ETag
    4. Optionally persists as new snapshot (unless dry_run=True)

    Args:
        greenhouse_id: Target greenhouse UUID
        request: Publish options (dry_run flag)
        session: Database session
        current_user: Authenticated user

    Returns:
        ConfigPublishResult with version, ETag, and complete payload

    Raises:
        HTTPException: 404 if greenhouse not found, 400 for validation errors
    """
    # Check greenhouse exists and user has access
    greenhouse_statement = select(Greenhouse).where(Greenhouse.id == greenhouse_id)
    greenhouse = session.exec(greenhouse_statement).first()
    if not greenhouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Greenhouse {greenhouse_id} not found",
        )

    # TODO: Add greenhouse ownership check once RLS is implemented
    # For now, any authenticated user can access any greenhouse

    builder = ConfigBuilder(session)
    errors = []
    warnings = []

    try:
        # Build configuration payload
        payload = builder.build_config(greenhouse_id)

        # Generate ETag
        etag = builder.generate_etag(payload)
        version = payload["version"]

        # If not dry run, persist snapshot
        published = False
        if not request.dry_run:
            # Check if this exact config already exists
            existing_statement = (
                select(ConfigSnapshot)
                .where(ConfigSnapshot.greenhouse_id == greenhouse_id)
                .where(ConfigSnapshot.etag == etag)
            )
            existing = session.exec(existing_statement).first()

            if existing:
                warnings.append(
                    f"Configuration unchanged from version {existing.version}"
                )
                published = False
                version = existing.version
            else:
                # Create new snapshot
                snapshot_data = ConfigSnapshotCreate(
                    greenhouse_id=greenhouse_id,
                    version=version,
                    etag=etag,
                    payload=payload,
                    created_by=current_user.id,
                )
                snapshot = ConfigSnapshot.model_validate(snapshot_data.model_dump())
                session.add(snapshot)
                session.commit()
                session.refresh(snapshot)
                published = True

        # Determine appropriate status code
        response_status = status.HTTP_201_CREATED if published else status.HTTP_200_OK

        result = ConfigPublishResult(
            published=published,
            version=version,
            etag=etag,
            errors=errors,
            warnings=warnings,
            payload=payload,
        )

        # Manually set status code for dry runs
        if request.dry_run:
            # FastAPI will use the default 201, but we want 200 for dry runs
            # We'll handle this at the response level
            pass

        return result

    except ValueError as e:
        errors.append(str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Configuration validation failed: {str(e)}",
        )
    except Exception as e:
        errors.append(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build configuration",
        )


@router.get(
    "/greenhouses/{greenhouse_id}/config/diff",
    response_model=ConfigDiff,
    responses={
        200: {"description": "JSON patch-like diff"},
        404: {"description": "Greenhouse not found"},
    },
)
def get_greenhouse_config_diff(
    greenhouse_id: uuid.UUID,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConfigDiff:
    """
    Diff current DB config vs last published snapshot.

    This endpoint compares the current database state with the most recently
    published configuration snapshot to identify changes.

    Args:
        greenhouse_id: Target greenhouse UUID
        session: Database session
        current_user: Authenticated user

    Returns:
        ConfigDiff with added, removed, and changed paths

    Raises:
        HTTPException: 404 if greenhouse not found
    """
    # Check greenhouse exists and user has access
    greenhouse_statement = select(Greenhouse).where(Greenhouse.id == greenhouse_id)
    greenhouse = session.exec(greenhouse_statement).first()
    if not greenhouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Greenhouse {greenhouse_id} not found",
        )

    # TODO: Add greenhouse ownership check once RLS is implemented

    # Get latest published snapshot
    latest_statement = (
        select(ConfigSnapshot)
        .where(ConfigSnapshot.greenhouse_id == greenhouse_id)
        .order_by(ConfigSnapshot.version.desc())
        .limit(1)
    )
    latest_snapshot = session.exec(latest_statement).first()

    if not latest_snapshot:
        # No published snapshots yet - everything is "added"
        return ConfigDiff(added=["*"], removed=[], changed=[])

    # Build current configuration
    builder = ConfigBuilder(session)
    try:
        current_payload = builder.build_config(greenhouse_id)
        published_payload = latest_snapshot.payload

        # Generate simple diff (placeholder implementation)
        # For MVP, we'll provide a basic comparison
        diff = _compute_config_diff(published_payload, current_payload)

        return diff

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute config diff: {str(e)}",
        )


def _compute_config_diff(
    old_config: dict[str, Any], new_config: dict[str, Any]
) -> ConfigDiff:
    """
    Compute simple diff between two config payloads.

    This is a placeholder implementation that provides basic change detection.
    A more sophisticated implementation could use libraries like jsondiff
    or provide field-level granular diffs.

    Args:
        old_config: Previously published configuration
        new_config: Current configuration

    Returns:
        ConfigDiff with change summary
    """
    added = []
    removed = []
    changed = []

    # Compare ETags for quick change detection
    old_version = old_config.get("version", 0)
    new_version = new_config.get("version", 0)

    if old_version != new_version:
        changed.append("version")

    # Compare major sections
    sections_to_check = [
        "greenhouse",
        "controllers",
        "sensors",
        "actuators",
        "fan_groups",
        "buttons",
        "state_rules",
        "baselines",
        "rails",
    ]

    for section in sections_to_check:
        old_section = old_config.get(section)
        new_section = new_config.get(section)

        if old_section != new_section:
            if old_section is None and new_section is not None:
                added.append(section)
            elif old_section is not None and new_section is None:
                removed.append(section)
            else:
                changed.append(section)

    # If no changes detected but configs differ, mark as changed
    if not added and not removed and not changed and old_config != new_config:
        changed.append("configuration")

    return ConfigDiff(added=added, removed=removed, changed=changed)
