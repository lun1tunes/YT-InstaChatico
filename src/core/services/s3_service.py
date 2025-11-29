"""
S3 Service for Document Storage

Handles file upload/download to SelectCloud S3-compatible storage.
"""

import logging
from typing import BinaryIO, Optional
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

from core.config import settings
from core.utils.time import now_db_utc

logger = logging.getLogger(__name__)


class S3Service:
    """Service for interacting with S3-compatible storage (SelectCloud)."""

    def __init__(self):
        """Initialize S3 client with SelectCloud configuration."""
        self.s3_client = boto3.client(
            's3',
            endpoint_url=f"https://{settings.s3.s3_url}",
            aws_access_key_id=settings.s3.aws_access_key_id,
            aws_secret_access_key=settings.s3.aws_secret_access_key,
            region_name=settings.s3.region,
            config=Config(signature_version='s3v4')
        )
        self.bucket_name = settings.s3.bucket_name

    def get_bucket_name(self) -> str:
        """Return configured bucket name."""
        return self.bucket_name

    def upload_file(
        self,
        file_obj: BinaryIO,
        s3_key: str,
        content_type: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Upload file to S3.

        Args:
            file_obj: File-like object to upload
            s3_key: S3 object key (path in bucket)
            content_type: MIME type of the file

        Returns:
            Tuple of (success: bool, url: str or error_message: str)
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )

            # Generate S3 URL
            s3_url = f"https://{settings.s3.s3_url}/{self.bucket_name}/{s3_key}"

            logger.info(f"Successfully uploaded file to S3: {s3_key}")
            return True, s3_url

        except ClientError as e:
            error_msg = f"Failed to upload file to S3: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def download_file(self, s3_key: str) -> tuple[bool, Optional[bytes], Optional[str]]:
        """
        Download file from S3.

        Args:
            s3_key: S3 object key

        Returns:
            Tuple of (success: bool, file_content: bytes or None, error_message: str or None)
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )

            file_content = response['Body'].read()
            logger.info(f"Successfully downloaded file from S3: {s3_key}")
            return True, file_content, None

        except ClientError as e:
            error_msg = f"Failed to download file from S3: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg

    def delete_file(self, s3_key: str) -> tuple[bool, Optional[str]]:
        """
        Delete file from S3.

        Args:
            s3_key: S3 object key

        Returns:
            Tuple of (success: bool, error_message: str or None)
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )

            logger.info(f"Successfully deleted file from S3: {s3_key}")
            return True, None

        except ClientError as e:
            error_msg = f"Failed to delete file from S3: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def generate_upload_key(self, filename: str, client_id: Optional[str] = None) -> str:
        """
        Generate S3 key for uploading a new document.

        Args:
            filename: Original filename
            client_id: Client identifier

        Returns:
            S3 key in format: documents/{client_id}/{timestamp}_{filename}
        """
        client_segment = client_id or "default"
        timestamp = now_db_utc().strftime("%Y%m%d_%H%M%S")
        # Sanitize filename
        safe_filename = filename.replace(" ", "_").replace("/", "_")
        return f"documents/{client_segment}/{timestamp}_{safe_filename}"


# Singleton instance
s3_service = S3Service()
