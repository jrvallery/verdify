import os
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session

from app.crud.observation import observation as crud_observation


class PresignedUploadService:
    """Service for generating presigned upload URLs for observation images"""

    def __init__(self):
        self.s3_enabled = os.getenv("S3_ENABLED", "false").lower() == "true"
        self.s3_bucket = os.getenv("S3_BUCKET_NAME", "verdify-uploads")
        self.local_upload_base = os.getenv("LOCAL_UPLOAD_BASE", "/app/static/uploads")
        self.default_expires_in = 3600  # 1 hour

    def generate_upload_url(
        self,
        session: Session,
        observation_id: UUID,
        user_id: UUID,
        filename: str | None = None,
    ) -> dict:
        """
        Generate presigned upload URL for observation image

        Returns:
            dict: {
                "upload_url": str,
                "expires_in_s": int
            }
        """
        # Validate observation exists and user has access
        observation = crud_observation.get(session, id=observation_id)
        if not observation:
            raise HTTPException(status_code=404, detail="Observation not found")

        # Validate ownership through zone crop
        if not crud_observation.validate_zone_crop_ownership(
            session, zone_crop_id=observation.zone_crop_id, user_id=user_id
        ):
            raise HTTPException(
                status_code=403, detail="Not authorized to upload to this observation"
            )

        if self.s3_enabled:
            return self._generate_s3_presigned_url(observation_id, filename)
        else:
            return self._generate_local_upload_url(observation_id, filename)

    def _generate_s3_presigned_url(
        self, observation_id: UUID, filename: str | None
    ) -> dict:
        """Generate S3 presigned URL (TODO: implement with boto3)"""
        # TODO: Implement actual S3 presigned URL generation
        # This is a placeholder for S3 implementation
        import boto3
        from botocore.exceptions import ClientError

        try:
            s3_client = boto3.client("s3")

            # Generate object key
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_ext = ""
            if filename:
                file_ext = filename.split(".")[-1] if "." in filename else ""
                file_ext = f".{file_ext}" if file_ext else ""

            object_key = f"observations/{observation_id}/{timestamp}{file_ext}"

            # Generate presigned URL
            presigned_url = s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.s3_bucket,
                    "Key": object_key,
                    "ContentType": "image/*",
                },
                ExpiresIn=self.default_expires_in,
            )

            return {
                "upload_url": presigned_url,
                "expires_in_s": self.default_expires_in,
            }

        except ClientError as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to generate upload URL: {str(e)}"
            )

    def _generate_local_upload_url(
        self, observation_id: UUID, filename: str | None
    ) -> dict:
        """Generate local upload URL for development"""
        # For local development, return a simple upload endpoint
        # The actual file upload would be handled by a separate endpoint
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_ext = ""
        if filename:
            file_ext = filename.split(".")[-1] if "." in filename else ""
            file_ext = f".{file_ext}" if file_ext else ""

        # In a real implementation, this would be signed or include a token
        upload_url = f"/api/v1/observations/{observation_id}/upload?timestamp={timestamp}&ext={file_ext}"

        return {"upload_url": upload_url, "expires_in_s": self.default_expires_in}


presigned_upload_service = PresignedUploadService()
