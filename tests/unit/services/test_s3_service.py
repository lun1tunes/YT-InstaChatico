"""
Unit tests for S3Service.
"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from io import BytesIO
from botocore.exceptions import ClientError

from core.services.s3_service import S3Service


@pytest.mark.unit
@pytest.mark.service
class TestS3Service:
    """Test S3Service methods."""

    @patch("core.services.s3_service.boto3.client")
    def test_upload_file_success(self, mock_boto_client):
        """Test successful file upload."""
        # Arrange
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        service = S3Service()
        file_obj = BytesIO(b"test file content")
        s3_key = "documents/client_123/20250101_120000_test.pdf"
        content_type = "application/pdf"

        # Act
        success, result = service.upload_file(file_obj, s3_key, content_type)

        # Assert
        assert success is True
        assert s3_key in result
        mock_s3.upload_fileobj.assert_called_once()
        call_args = mock_s3.upload_fileobj.call_args
        assert call_args[0][0] == file_obj
        assert call_args[1]["ExtraArgs"]["ContentType"] == content_type

    @patch("core.services.s3_service.boto3.client")
    def test_upload_file_without_content_type(self, mock_boto_client):
        """Test file upload without content type."""
        # Arrange
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        service = S3Service()
        file_obj = BytesIO(b"test content")
        s3_key = "documents/client_123/test.txt"

        # Act
        success, result = service.upload_file(file_obj, s3_key, content_type=None)

        # Assert
        assert success is True
        mock_s3.upload_fileobj.assert_called_once()
        call_args = mock_s3.upload_fileobj.call_args
        assert call_args[1]["ExtraArgs"] == {}

    @patch("core.services.s3_service.boto3.client")
    def test_upload_file_client_error(self, mock_boto_client):
        """Test file upload handles ClientError."""
        # Arrange
        mock_s3 = MagicMock()
        mock_s3.upload_fileobj.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "The specified bucket does not exist"}},
            "upload_fileobj"
        )
        mock_boto_client.return_value = mock_s3

        service = S3Service()
        file_obj = BytesIO(b"test content")
        s3_key = "documents/test.pdf"

        # Act
        success, error_msg = service.upload_file(file_obj, s3_key)

        # Assert
        assert success is False
        assert "Failed to upload file to S3" in error_msg
        assert "NoSuchBucket" in error_msg or "bucket" in error_msg.lower()

    @patch("core.services.s3_service.boto3.client")
    def test_download_file_success(self, mock_boto_client):
        """Test successful file download."""
        # Arrange
        mock_s3 = MagicMock()
        mock_body = Mock()
        mock_body.read.return_value = b"downloaded file content"
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_boto_client.return_value = mock_s3

        service = S3Service()
        s3_key = "documents/client_123/test.pdf"

        # Act
        success, content, error = service.download_file(s3_key)

        # Assert
        assert success is True
        assert content == b"downloaded file content"
        assert error is None
        mock_s3.get_object.assert_called_once_with(
            Bucket=service.bucket_name,
            Key=s3_key
        )

    @patch("core.services.s3_service.boto3.client")
    def test_download_file_client_error(self, mock_boto_client):
        """Test file download handles ClientError."""
        # Arrange
        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist"}},
            "get_object"
        )
        mock_boto_client.return_value = mock_s3

        service = S3Service()
        s3_key = "documents/nonexistent.pdf"

        # Act
        success, content, error_msg = service.download_file(s3_key)

        # Assert
        assert success is False
        assert content is None
        assert "Failed to download file from S3" in error_msg
        assert "NoSuchKey" in error_msg or "key" in error_msg.lower()

    @patch("core.services.s3_service.boto3.client")
    def test_delete_file_success(self, mock_boto_client):
        """Test successful file deletion."""
        # Arrange
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        service = S3Service()
        s3_key = "documents/client_123/test.pdf"

        # Act
        success, error = service.delete_file(s3_key)

        # Assert
        assert success is True
        assert error is None
        mock_s3.delete_object.assert_called_once_with(
            Bucket=service.bucket_name,
            Key=s3_key
        )

    @patch("core.services.s3_service.boto3.client")
    def test_delete_file_client_error(self, mock_boto_client):
        """Test file deletion handles ClientError."""
        # Arrange
        mock_s3 = MagicMock()
        mock_s3.delete_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "delete_object"
        )
        mock_boto_client.return_value = mock_s3

        service = S3Service()
        s3_key = "documents/client_123/test.pdf"

        # Act
        success, error_msg = service.delete_file(s3_key)

        # Assert
        assert success is False
        assert "Failed to delete file from S3" in error_msg
        assert "AccessDenied" in error_msg or "access" in error_msg.lower()

    @patch("core.services.s3_service.boto3.client")
    @patch("core.services.s3_service.now_db_utc")
    def test_generate_upload_key(self, mock_now, mock_boto_client):
        """Test S3 key generation."""
        # Arrange
        from datetime import datetime
        mock_now.return_value = datetime(2025, 1, 15, 14, 30, 45)

        service = S3Service()
        filename = "Test Document.pdf"
        client_id = "client_123"

        # Act
        s3_key = service.generate_upload_key(filename, client_id)

        # Assert
        assert s3_key == "documents/client_123/20250115_143045_Test_Document.pdf"
        assert " " not in s3_key  # Spaces should be replaced
        assert s3_key.startswith(f"documents/{client_id}/")

    @patch("core.services.s3_service.boto3.client")
    @patch("core.services.s3_service.now_db_utc")
    def test_generate_upload_key_sanitizes_filename(self, mock_now, mock_boto_client):
        """Test that generate_upload_key sanitizes filename."""
        # Arrange
        from datetime import datetime
        mock_now.return_value = datetime(2025, 1, 15, 14, 30, 45)

        service = S3Service()
        filename = "path/to/file name.pdf"
        client_id = "client_456"

        # Act
        s3_key = service.generate_upload_key(filename, client_id)

        # Assert
        assert s3_key == "documents/client_456/20250115_143045_path_to_file_name.pdf"
        assert "/" not in s3_key.split("/", 2)[2]  # No slashes in filename part
        assert " " not in s3_key  # No spaces
