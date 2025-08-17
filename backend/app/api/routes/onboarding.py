import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.api.deps import get_current_user, get_db
from app.core.security import (
    create_device_token_hash,
    generate_claim_code,
    generate_device_token,
)
from app.crud.controller import get_controller
from app.crud.greenhouses import get_greenhouse
from app.models import (
    Controller,
    ControllerClaimRequest,
    ControllerClaimResponse,
    ControllerPublic,
    HelloRequest,
    HelloResponse,
    TokenExchangeRequest,
    TokenExchangeResponse,
    TokenRotateResponse,
    User,
)

router = APIRouter()


def generate_etag(content_type: str, version: int) -> str:
    """Generate ETag for config/plan resources.

    Args:
        content_type: "config" or "plan"
        version: Version number

    Returns:
        ETag string in format: content_type:v{version}:{sha8}
    """
    # For now, generate a simple hash based on current time
    # In production, this would be based on actual content
    content = f"{content_type}-{version}-{datetime.now(timezone.utc).isoformat()}"
    sha_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
    return f"{content_type}:v{version}:{sha_hash}"


@router.post(
    "/hello", response_model=HelloResponse, status_code=200, tags=["Onboarding"]
)
def announce_controller(
    request: HelloRequest,
    db: Session = Depends(get_db),
) -> Any:
    """Controller announces itself on first boot.

    Public endpoint (no authentication). Creates or finds controller record.
    Returns claim status and controller info if already claimed.
    """
    # Validate device_name pattern
    if not request.device_name.startswith("verdify-") or len(request.device_name) != 14:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device_name format. Must be verdify-xxxxxx",
        )

    # Look for existing controller by device_name
    controller = db.exec(
        select(Controller).where(Controller.device_name == request.device_name)
    ).first()

    current_time = datetime.now(timezone.utc)

    if controller:
        # Update last_seen and firmware info
        controller.last_seen = current_time
        controller.firmware = request.firmware
        controller.hardware_profile = request.hardware_profile

        if controller.claim_code and controller.greenhouse_id:
            # Controller is claimed
            db.add(controller)
            db.commit()

            return HelloResponse(
                status="claimed",
                controller_uuid=controller.id,
                greenhouse_id=controller.greenhouse_id,
                message="Controller already claimed",
            )
        else:
            # Controller exists but not claimed yet
            db.add(controller)
            db.commit()

            return HelloResponse(
                status="pending", retry_after_s=30, message="Waiting for user claim"
            )
    else:
        # Create new controller record with initial data
        controller = Controller(
            device_name=request.device_name,
            label=f"Controller {request.device_name}",
            hardware_profile=request.hardware_profile,
            firmware=request.firmware,
            first_seen=current_time,
            last_seen=current_time,
            # Will be set during claim process
            greenhouse_id=None,  # type: ignore
            claim_code=None,
        )

        db.add(controller)
        db.commit()

        return HelloResponse(
            status="pending",
            retry_after_s=30,
            message="Controller registered, waiting for user claim",
        )


@router.post(
    "/controllers/claim",
    response_model=ControllerClaimResponse,
    status_code=201,
    tags=["Onboarding"],
)
def claim_controller(
    request: ControllerClaimRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Claim a controller to a greenhouse and issue device_token.

    Requires JWT authentication. Sets claim_code and device_token.
    """
    # Verify greenhouse exists and user has access
    greenhouse = get_greenhouse(session=db, id=request.greenhouse_id)
    if not greenhouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found"
        )

    # Check if user owns the greenhouse (or is superuser)
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to claim controllers for this greenhouse",
        )

    # Find controller by device_name
    controller = db.exec(
        select(Controller).where(Controller.device_name == request.device_name)
    ).first()

    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Controller with device_name {request.device_name} not found. Make sure it has announced itself via /hello first.",
        )

    # Check if controller is already claimed
    if controller.greenhouse_id and controller.claim_code:
        if controller.greenhouse_id == request.greenhouse_id:
            # Already claimed to the same greenhouse - return existing info
            if controller.device_token_hash:
                # Don't return the actual token since we only store the hash
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Controller already claimed. Use token-exchange endpoint if needed.",
                )
        else:
            # Claimed to different greenhouse
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Controller already claimed to a different greenhouse",
            )

    # Generate new claim code and device token
    claim_code = generate_claim_code()
    device_token = generate_device_token()
    device_token_hash = create_device_token_hash(device_token)

    current_time = datetime.now(timezone.utc)
    expires_at = current_time + timedelta(days=180)  # 6 months expiry

    # Update controller with claim information
    controller.greenhouse_id = request.greenhouse_id
    controller.claim_code = claim_code
    controller.device_token_hash = device_token_hash
    controller.token_expires_at = expires_at
    controller.claimed_at = current_time
    controller.claimed_by = current_user.id
    controller.token_exchange_completed = False

    db.add(controller)
    db.commit()
    db.refresh(controller)

    return ControllerClaimResponse(
        controller=ControllerPublic.model_validate(controller),
        device_token=device_token,
        expires_at=expires_at,
    )


@router.post(
    "/controllers/{controller_id}/token-exchange",
    response_model=TokenExchangeResponse,
    tags=["Onboarding"],
)
def exchange_controller_token(
    controller_id: str,
    request: TokenExchangeRequest,
    db: Session = Depends(get_db),
) -> Any:
    """One-time exchange of claim_code + device_name for long-lived device_token & initial ETags.

    Public endpoint. Idempotent: returns same result on repeated calls after first success.
    First successful call returns 201, subsequent calls return 200.
    """
    try:
        controller_uuid = uuid.UUID(controller_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid controller ID format",
        )

    # Find controller by ID
    controller = get_controller(session=db, controller_id=controller_uuid)
    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Controller not found"
        )

    # Verify device_name matches
    if controller.device_name != request.device_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device name does not match controller record",
        )

    # Verify claim_code matches
    if not controller.claim_code or controller.claim_code != request.claim_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid claim code"
        )

    # Check if controller is claimed
    if not controller.greenhouse_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Controller not yet claimed to a greenhouse",
        )

    # Check if token has expired
    current_time = datetime.now(timezone.utc)
    if controller.token_expires_at:
        # Ensure both datetimes are timezone-aware for comparison
        expires_at = controller.token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < current_time:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Device token has expired. Contact admin to rotate token.",
            )

    # Generate ETags for config and plan
    config_etag = generate_etag("config", 1)
    plan_etag = generate_etag("plan", 1)

    if controller.token_exchange_completed:
        # Idempotent case - already exchanged
        response = TokenExchangeResponse(
            device_token="[ALREADY_ISSUED]",  # Don't return actual token since we only store hash
            config_etag=config_etag,
            plan_etag=plan_etag,
            expires_at=controller.token_expires_at or datetime.now(timezone.utc),
        )
        return Response(
            status_code=200,
            content=response.model_dump_json(),
            media_type="application/json",
        )
    else:
        # First exchange - mark as completed
        controller.token_exchange_completed = True
        db.add(controller)
        db.commit()

        # Return the device token (this is the only time we can return it)
        if not controller.device_token_hash:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Device token not available. Controller may need to be reclaimed.",
            )

        response = TokenExchangeResponse(
            device_token="[TOKEN_EXCHANGED]",  # In real implementation, would return actual token
            config_etag=config_etag,
            plan_etag=plan_etag,
            expires_at=controller.token_expires_at or datetime.now(timezone.utc),
        )
        return Response(
            status_code=201,
            content=response.model_dump_json(),
            media_type="application/json",
        )


@router.post(
    "/controllers/{controller_id}/rotate-token",
    response_model=TokenRotateResponse,
    tags=["Authentication"],
)
def rotate_controller_token(
    controller_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Rotate device token for controller.

    Requires JWT authentication. Generates new device token.
    """
    try:
        controller_uuid = uuid.UUID(controller_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid controller ID format",
        )

    controller = get_controller(session=db, controller_id=controller_uuid)
    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Controller not found"
        )

    # Check if user has access to the controller's greenhouse
    if controller.greenhouse and not (
        current_user.is_superuser or controller.greenhouse.user_id == current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to rotate token for this controller",
        )

    # Generate new device token
    device_token = generate_device_token()
    device_token_hash = create_device_token_hash(device_token)

    current_time = datetime.now(timezone.utc)
    expires_at = current_time + timedelta(days=180)  # 6 months expiry

    # Update controller
    controller.device_token_hash = device_token_hash
    controller.token_expires_at = expires_at
    controller.token_exchange_completed = False  # Require re-exchange

    db.add(controller)
    db.commit()

    return TokenRotateResponse(device_token=device_token, expires_at=expires_at)


@router.post(
    "/controllers/{controller_id}/revoke-token",
    status_code=204,
    tags=["Authentication"],
)
def revoke_controller_token(
    controller_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Revoke device token for controller.

    Requires JWT authentication. Invalidates device token.
    """
    try:
        controller_uuid = uuid.UUID(controller_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid controller ID format",
        )

    controller = get_controller(session=db, controller_id=controller_uuid)
    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Controller not found"
        )

    # Check if user has access to the controller's greenhouse
    if controller.greenhouse and not (
        current_user.is_superuser or controller.greenhouse.user_id == current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to revoke token for this controller",
        )

    # Revoke token by clearing it
    controller.device_token_hash = None
    controller.token_expires_at = None
    controller.token_exchange_completed = False

    db.add(controller)
    db.commit()
