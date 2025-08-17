"""
Device config fetch endpoints.

Provides controllers with their configuration data using ETag-based caching.
Controllers authenticate using X-Device-Token and can fetch configs by device name
or using the "me" alias.
"""

import gzip
import json
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response
from sqlmodel import Session, select

from app.api.deps import CurrentDevice, SessionDep
from app.models import ConfigSnapshot

router = APIRouter()


def get_latest_config_snapshot(
    session: Session, greenhouse_id: str
) -> ConfigSnapshot | None:
    """Get the latest config snapshot for a greenhouse."""
    statement = (
        select(ConfigSnapshot)
        .where(ConfigSnapshot.greenhouse_id == greenhouse_id)
        .order_by(ConfigSnapshot.version.desc())
        .limit(1)
    )
    return session.exec(statement).first()


def create_config_response(
    snapshot: ConfigSnapshot,
    accept_encoding: str | None = None,
) -> tuple[dict, dict[str, str]]:
    """Create config response with proper headers and optional gzip compression."""
    payload = snapshot.payload
    headers = {
        "ETag": f'"{snapshot.etag}"',
        "Last-Modified": snapshot.created_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "Cache-Control": "private, must-revalidate",
    }

    # Optional gzip compression (phase-2 feature)
    if accept_encoding and "gzip" in accept_encoding:
        json_content = json.dumps(payload, separators=(",", ":"))
        compressed_content = gzip.compress(json_content.encode("utf-8"))
        headers["Content-Encoding"] = "gzip"
        # Note: FastAPI will handle the actual gzip response automatically
        # This is a placeholder for future implementation

    return payload, headers


@router.get(
    "/controllers/by-name/{device_name}/config",
    summary="Get config by device name",
    description="Fetch configuration for controller by device name. Uses ETag for caching.",
    responses={
        200: {"description": "Configuration retrieved successfully"},
        304: {"description": "Not modified (ETag match)"},
        401: {"description": "Device token required"},
        404: {"description": "Device or config not found"},
    },
    tags=["Config"],
)
def get_config_by_device_name(
    device_name: str,
    session: SessionDep,
    current_device: CurrentDevice,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    accept_encoding: Annotated[str | None, Header(alias="Accept-Encoding")] = None,
):
    """
    Get configuration for a controller by device name.

    Controllers can fetch their configuration using their device_name.
    The device token must belong to a controller with the specified device_name.

    Args:
        device_name: Device name in format "verdify-aabbcc"
        session: Database session
        current_device: Controller from device token auth
        if_none_match: ETag for conditional requests
        accept_encoding: Accept-Encoding header for optional gzip

    Returns:
        Configuration payload with ETag headers or 304 if not modified
    """
    # Verify the device token matches the requested device name
    if current_device.device_name != device_name:
        raise HTTPException(
            status_code=403,
            detail="Device token does not match requested device name",
        )

    # Ensure device is associated with a greenhouse
    if not current_device.greenhouse_id:
        raise HTTPException(
            status_code=404,
            detail="Controller not associated with a greenhouse",
        )

    # Get latest config snapshot for the greenhouse
    snapshot = get_latest_config_snapshot(session, str(current_device.greenhouse_id))
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail="No configuration snapshot found for this greenhouse",
        )

    # Check ETag for conditional requests
    if if_none_match and if_none_match.strip('"') == snapshot.etag:
        return Response(status_code=304)

    # Create response with proper headers
    payload, headers = create_config_response(snapshot, accept_encoding)

    return Response(
        content=json.dumps(payload, separators=(",", ":")),
        media_type="application/json",
        headers=headers,
    )


@router.get(
    "/controllers/me/config",
    summary="Get config for current device",
    description="Fetch configuration for the authenticated controller. Uses ETag for caching.",
    responses={
        200: {"description": "Configuration retrieved successfully"},
        304: {"description": "Not modified (ETag match)"},
        401: {"description": "Device token required"},
        404: {"description": "Config not found"},
    },
    tags=["Config"],
)
def get_config_for_current_device(
    session: SessionDep,
    current_device: CurrentDevice,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    accept_encoding: Annotated[str | None, Header(alias="Accept-Encoding")] = None,
):
    """
    Get configuration for the authenticated controller.

    This is a convenience endpoint that allows controllers to fetch their
    configuration without needing to specify their device_name.

    Args:
        session: Database session
        current_device: Controller from device token auth
        if_none_match: ETag for conditional requests
        accept_encoding: Accept-Encoding header for optional gzip

    Returns:
        Configuration payload with ETag headers or 304 if not modified
    """
    # Ensure device is associated with a greenhouse
    if not current_device.greenhouse_id:
        raise HTTPException(
            status_code=404,
            detail="Controller not associated with a greenhouse",
        )

    # Get latest config snapshot for the greenhouse
    snapshot = get_latest_config_snapshot(session, str(current_device.greenhouse_id))
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail="No configuration snapshot found for this greenhouse",
        )

    # Check ETag for conditional requests
    if if_none_match and if_none_match.strip('"') == snapshot.etag:
        return Response(status_code=304)

    # Create response with proper headers
    payload, headers = create_config_response(snapshot, accept_encoding)

    return Response(
        content=json.dumps(payload, separators=(",", ":")),
        media_type="application/json",
        headers=headers,
    )
