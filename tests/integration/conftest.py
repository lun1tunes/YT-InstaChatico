import base64
import hashlib
import hmac
import os
from typing import Any, Dict, List, Optional

import pytest
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import settings
from core.container import get_container, reset_container
from core.models import (
    CommentClassification,
    Document,
    InstagramComment,
    Media,
    db_helper,
)
from core.utils.time import now_db_utc
from core.logging_config import configure_logging
from main import app
from tests.integration.json_api_helpers import auth_headers


class StubTaskQueue:
    """In-memory Celery replacement for integration tests."""

    def __init__(self) -> None:
        self.enqueued: List[Dict[str, Any]] = []

    def enqueue(self, task_name: str, *args, countdown: Optional[int] = None, **kwargs) -> str:
        entry = {
            "task": task_name,
            "args": args,
            "kwargs": kwargs,
            "countdown": countdown,
        }
        self.enqueued.append(entry)
        return f"task-{len(self.enqueued)}"


class StubMediaService:
    """Minimal media service that stores media records in the test database."""

    def __init__(self) -> None:
        self.requested: List[str] = []
        self.refreshed: List[str] = []

    async def get_or_create_media(self, media_id: str, session: AsyncSession) -> Media:
        self.requested.append(media_id)
        media = await session.get(Media, media_id)
        if media:
            return media

        media = Media(
            id=media_id,
            permalink=f"https://instagram.com/p/{media_id}",
            caption="Test caption",
            media_url=f"https://cdn.test/{media_id}.jpg",
            media_type="IMAGE",
            comments_count=0,
            like_count=0,
            shortcode=f"short_{media_id[-5:]}",
            is_processing_enabled=True,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.flush()
        return media

    async def refresh_media_urls(self, media_id: str, session: AsyncSession) -> Optional[Media]:
        self.refreshed.append(media_id)
        return await self.get_or_create_media(media_id, session)

    async def set_comment_status(self, media_id: str, enabled: bool, session: AsyncSession) -> Dict[str, Any]:
        media = await self.get_or_create_media(media_id, session)
        media.is_comment_enabled = enabled
        await session.flush()
        return {"success": True, "media_id": media_id, "is_comment_enabled": enabled}


class StubInstagramService:
    """Instagram API stub covering the methods used in tests."""

    def __init__(self) -> None:
        self.hidden: List[str] = []
        self.replies: List[Dict[str, Any]] = []
        self.closed = False
        self.deleted: List[str] = []
        self.reply_counter = 0
        self.insights_calls: List[Dict[str, Any]] = []
        self.insights_responses: Dict[str, Dict[str, Any]] = {}
        self.insights_default_response: Optional[Dict[str, Any]] = None
        self.insights_error: Optional[Exception] = None
        self.account_profile_calls: int = 0
        self.account_profile_response: Dict[str, Any] = {
            "success": True,
            "data": {
                "username": "test_account",
                "media_count": 0,
                "followers_count": 0,
                "follows_count": 0,
                "id": "acct",
            },
        }
        self.account_profile_error: Optional[Exception] = None

    async def send_reply_to_comment(self, comment_id: str, message: str) -> Dict[str, Any]:
        self.reply_counter += 1
        reply_id = f"reply-{comment_id}-{self.reply_counter}"
        self.replies.append({"comment_id": comment_id, "message": message, "reply_id": reply_id})
        return {"success": True, "reply_id": reply_id, "response": {"id": reply_id}}

    async def hide_comment(self, comment_id: str, hide: bool = True) -> Dict[str, Any]:
        if hide:
            if comment_id not in self.hidden:
                self.hidden.append(comment_id)
        else:
            if comment_id in self.hidden:
                self.hidden.remove(comment_id)
        return {"success": True}

    async def delete_comment(self, comment_id: str) -> Dict[str, Any]:
        if comment_id not in self.deleted:
            self.deleted.append(comment_id)
        return {"success": True}

    async def close(self) -> None:
        self.closed = True

    async def get_media_info(self, media_id: str) -> Dict[str, Any]:
        return {
            "success": True,
            "media_info": {
                "id": media_id,
                "media_type": "IMAGE",
                "media_url": f"https://cdn.test/{media_id}.jpg",
                "permalink": f"https://instagram.com/p/{media_id}",
            },
        }

    async def set_media_comment_status(self, media_id: str, enabled: bool) -> Dict[str, Any]:
        return {"success": True, "media_id": media_id, "is_comment_enabled": enabled}

    async def delete_comment_reply(self, reply_id: str) -> Dict[str, Any]:
        self.replies = [r for r in self.replies if r.get("reply_id") != reply_id]
        return {"success": True, "reply_id": reply_id}

    async def get_account_profile(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        self.account_profile_calls += 1
        if self.account_profile_error:
            raise self.account_profile_error
        return self.account_profile_response

    async def get_insights(self, account_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self.insights_calls.append({"account_id": account_id, "params": params})
        if self.insights_error:
            raise self.insights_error

        metric = params.get("metric")
        response = self.insights_responses.get(metric) if metric else None
        if response is None:
            response = self.insights_default_response

        if response is None:
            return {
                "success": True,
                "data": {
                    "metric": metric or "",
                    "params": params,
                },
            }

        return response


class StubS3Service:
    """S3 facade stub used by document endpoints."""

    def __init__(self) -> None:
        self.uploaded: Dict[str, bytes] = {}
        self.deleted: List[str] = []
        self.bucket_name = settings.s3.bucket_name
        self.s3_url = settings.s3.s3_url

    def get_bucket_name(self) -> str:
        return self.bucket_name

    def upload_file(self, file_obj, s3_key: str, content_type: Optional[str] = None) -> tuple[bool, Optional[str]]:
        data = file_obj.read()
        self.uploaded[s3_key] = data
        return True, f"https://{self.s3_url}/{self.bucket_name}/{s3_key}"

    def download_file(self, s3_key: str) -> tuple[bool, Optional[bytes], Optional[str]]:
        data = self.uploaded.get(s3_key, b"dummy content")
        return True, data, None

    def delete_file(self, s3_key: str) -> tuple[bool, Optional[str]]:
        self.deleted.append(s3_key)
        return True, None

    def generate_upload_key(self, filename: str, client_id: Optional[str] = None) -> str:
        client_segment = client_id or "default"
        safe_name = filename.replace(" ", "_").replace("/", "_")
        timestamp = now_db_utc().strftime("%Y%m%d_%H%M%S")
        return f"documents/{client_segment}/{timestamp}_{safe_name}"


class StubDocumentProcessingService:
    """Lightweight processor that turns bytes into markdown."""

    def detect_document_type(self, filename: str) -> str:
        extension = os.path.splitext(filename)[1].lower()
        return {
            ".pdf": "pdf",
            ".txt": "txt",
            ".csv": "csv",
            ".xlsx": "excel",
            ".xls": "excel",
            ".docx": "word",
        }.get(extension, "other")

    def process_document(
        self,
        file_content: bytes,
        filename: str,
        document_type: str,
    ) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        if document_type == "other":
            return False, None, None, "Unsupported document type"

        markdown = f"# Processed {filename}\n\n{base64.b64encode(file_content).decode()}"
        content_hash = hashlib.sha256(file_content).hexdigest()
        return True, markdown, content_hash, None


class StubTelegramService:
    """Telegram service stub returning canned responses."""

    def __init__(self) -> None:
        self.should_fail_notification = False
        self.notifications: List[Dict[str, Any]] = []
        self.log_alerts: List[Dict[str, Any]] = []

    async def test_connection(self) -> Dict[str, Any]:
        return {"success": True, "bot_info": {"id": 42, "username": "test_bot"}, "chat_id": "chat-1"}

    async def send_urgent_issue_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        if self.should_fail_notification:
            return {"success": False, "error": "forced failure"}
        self.notifications.append(comment_data)
        return {"success": True, "message_id": 999, "response": {"ok": True}}

    async def send_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.send_urgent_issue_notification(comment_data)

    async def send_log_alert(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_alerts.append(log_data)
        return {"success": True}


@pytest.fixture
def sign_payload():
    """Return helper for generating X-Hub signature headers."""

    def _sign(body: bytes) -> str:
        digest = hmac.new(settings.app_secret.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    return _sign


@pytest.fixture
async def integration_environment(test_engine):
    """Configure dependency injection overrides and database for integration tests."""
    original_engine = db_helper.engine
    original_session_factory = db_helper.session_factory
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    db_helper.engine = test_engine
    db_helper.session_factory = session_factory

    original_secret = settings.app_secret
    original_verify_token = settings.app_webhook_verify_token
    original_development_mode = os.environ.get("DEVELOPMENT_MODE")
    original_bucket = settings.s3.bucket_name
    original_s3_url = settings.s3.s3_url
    original_base_account_id = settings.instagram.base_account_id
    original_json_api_secret = settings.json_api.secret_key
    original_json_api_algorithm = settings.json_api.algorithm
    original_json_api_expire = settings.json_api.expire_minutes

    settings.app_secret = "test_app_secret"
    settings.app_webhook_verify_token = "verify_token"
    os.environ["DEVELOPMENT_MODE"] = "false"
    settings.s3.bucket_name = "test-bucket"
    settings.s3.s3_url = "s3.test.local"
    settings.instagram.base_account_id = "acct"
    settings.json_api.secret_key = "test-json-secret"
    settings.json_api.algorithm = "HS256"
    settings.json_api.expire_minutes = 60

    reset_container()
    container = get_container()

    task_queue = StubTaskQueue()
    media_service = StubMediaService()
    instagram_service = StubInstagramService()
    s3_service = StubS3Service()
    document_processor = StubDocumentProcessingService()
    telegram_service = StubTelegramService()

    container.task_queue.override(providers.Object(task_queue))
    container.media_service.override(providers.Object(media_service))
    container.instagram_service.override(providers.Object(instagram_service))
    container.s3_service.override(providers.Object(s3_service))
    container.document_processing_service.override(providers.Object(document_processor))
    container.telegram_service.override(providers.Object(telegram_service))
    container.log_alert_service.override(providers.Object(telegram_service))
    container.db_session_factory.override(providers.Callable(lambda: session_factory))
    container.db_engine.override(providers.Callable(lambda: test_engine))

    json_api_env = {
        "json_api_secret": settings.json_api.secret_key,
        "json_api_algorithm": settings.json_api.algorithm,
        "json_api_expire": settings.json_api.expire_minutes,
    }
    default_auth_headers = auth_headers(json_api_env)

    try:
        configure_logging()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield {
                "client": client,
                "session_factory": session_factory,
                "task_queue": task_queue,
                "media_service": media_service,
                "instagram_service": instagram_service,
                "s3_service": s3_service,
                "document_processor": document_processor,
                "telegram_service": telegram_service,
                "auth_headers": default_auth_headers,
                **json_api_env,
            }
    finally:
        container.task_queue.reset_override()
        container.media_service.reset_override()
        container.instagram_service.reset_override()
        container.s3_service.reset_override()
        container.document_processing_service.reset_override()
        container.telegram_service.reset_override()
        container.log_alert_service.reset_override()
        container.db_session_factory.reset_override()
        container.db_engine.reset_override()

        reset_container()
        db_helper.engine = original_engine
        db_helper.session_factory = original_session_factory
        settings.app_secret = original_secret
        settings.app_webhook_verify_token = original_verify_token
        settings.s3.bucket_name = original_bucket
        settings.s3.s3_url = original_s3_url
        settings.instagram.base_account_id = original_base_account_id
        settings.json_api.secret_key = original_json_api_secret
        settings.json_api.algorithm = original_json_api_algorithm
        settings.json_api.expire_minutes = original_json_api_expire

        if original_development_mode is None:
            os.environ.pop("DEVELOPMENT_MODE", None)
        else:
            os.environ["DEVELOPMENT_MODE"] = original_development_mode


__all__ = [
    "integration_environment",
    "sign_payload",
    "StubTaskQueue",
    "StubMediaService",
    "StubInstagramService",
    "StubS3Service",
    "StubDocumentProcessingService",
    "StubTelegramService",
]
