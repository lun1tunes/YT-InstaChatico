"""
Pytest configuration and shared fixtures for all tests.

This file provides:
- Database fixtures (in-memory SQLite for fast tests)
- Mock services and external APIs
- Test data factories
- FastAPI test client
- Celery test setup
"""

import asyncio
import os
import pytest
import pytest_asyncio
import sys
from datetime import datetime, timezone
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

# Prepopulate required env vars for settings before imports
os.environ.setdefault("APP_SECRET", "dummy_app_secret")
os.environ.setdefault("TOKEN", "dummy_token")
os.environ.setdefault("YOUTUBE_CLIENT_ID", "dummy_youtube_client_id")
os.environ.setdefault("YOUTUBE_CLIENT_SECRET", "dummy_youtube_client_secret")
os.environ.setdefault("YOUTUBE_REFRESH_TOKEN", "dummy_youtube_refresh_token")
os.environ.setdefault("YOUTUBE_API_KEY", "dummy_youtube_api_key")
os.environ.setdefault("YOUTUBE_CHANNEL_ID", "dummy_youtube_channel_id")
os.environ.setdefault("OAUTH_ENCRYPTION_KEY", "1p_UUU0j5OJ9SxWwtUWFI7Ak4luuL8EA3twJY86W0Z0=")

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import event, JSON
from sqlalchemy.dialects import postgresql
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from faker import Faker

# Import your app modules
from core.models.base import Base
from core.models import (
    InstagramComment,
    CommentClassification,
    QuestionAnswer,
    Media,
    Document,
    ProductEmbedding,
    ExpiredToken,
    InstrumentTokenUsage,
)
from core.models.comment_classification import ProcessingStatus
from core.models.question_answer import AnswerStatus
from core.config import settings
from core.container import Container, get_container, reset_container
from main import app

fake = Faker()


# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest.fixture
async def test_engine():
    """Create an in-memory SQLite database engine for testing."""
    # Use in-memory SQLite with asyncio support
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Register event listener to convert JSONB to JSON for SQLite compatibility
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_jsonb_compat(dbapi_conn, connection_record):
        """Convert PostgreSQL JSONB columns to JSON for SQLite."""
        # This runs on connect - SQLite will use JSON type instead of JSONB
        pass

    # Create all tables with JSONB→JSON conversion
    async with engine.begin() as conn:
        # Replace JSONB with JSON for SQLite before creating tables
        def _create_tables_with_json(connection):
            # Temporarily replace JSONB type with JSON for SQLite
            from sqlalchemy.dialects import sqlite

            # Save original JSONB type
            original_type_map = postgresql.JSONB

            # Override JSONB to use JSON in SQLite
            for table in Base.metadata.tables.values():
                for column in table.columns:
                    if hasattr(column.type, '__class__') and column.type.__class__.__name__ == 'JSONB':
                        column.type = JSON()

            Base.metadata.create_all(connection)

        await conn.run_sync(_create_tables_with_json)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


# ============================================================================
# TEST DATA FACTORIES
# ============================================================================


@pytest.fixture
def instagram_comment_factory(db_session):
    """Factory for creating test Instagram comments."""
    async def _create_comment(
        comment_id: str = None,
        media_id: str = None,
        user_id: str = None,
        username: str = None,
        text: str = None,
        parent_id: str = None,
        conversation_id: str = None,
        **kwargs
    ) -> InstagramComment:
        comment = InstagramComment(
            id=comment_id or fake.uuid4(),
            media_id=media_id or fake.uuid4(),
            user_id=user_id or fake.uuid4(),
            username=username or fake.user_name(),
            text=text or fake.sentence(),
            created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
            raw_data=kwargs.get("raw_data", {}),
            parent_id=parent_id,
            conversation_id=conversation_id,
            is_hidden=kwargs.get("is_hidden", False),
            is_deleted=kwargs.get("is_deleted", False),
        )
        db_session.add(comment)
        await db_session.commit()
        await db_session.refresh(comment)
        return comment

    return _create_comment


@pytest.fixture
def media_factory(db_session):
    """Factory for creating test Media objects."""
    sentinel = object()

    async def _create_media(
        media_id: str = None,
        media_type: str = "IMAGE",
        media_url=sentinel,
        caption: str = None,
        **kwargs
    ) -> Media:
        if media_url is sentinel:
            actual_media_url = fake.image_url()
        else:
            actual_media_url = media_url

        media = Media(
            id=media_id or fake.uuid4(),
            media_type=media_type,
            media_url=actual_media_url,
            caption=caption or fake.text(),
            permalink=kwargs.get("permalink", fake.url()),
            media_context=kwargs.get("media_context"),
            children_media_urls=kwargs.get("children_media_urls"),
            comments_count=kwargs.get("comments_count"),
            like_count=kwargs.get("like_count"),
            shortcode=kwargs.get("shortcode"),
            posted_at=kwargs.get("posted_at") or kwargs.get("timestamp"),
            is_comment_enabled=kwargs.get("is_comment_enabled"),
            is_processing_enabled=kwargs.get("is_processing_enabled", True),
            username=kwargs.get("username"),
            owner=kwargs.get("owner"),
            raw_data=kwargs.get("raw_data"),
            analysis_requested_at=kwargs.get("analysis_requested_at"),
        )
        db_session.add(media)
        await db_session.commit()
        await db_session.refresh(media)
        return media

    return _create_media


@pytest.fixture
def classification_factory(db_session):
    """Factory for creating test comment classifications."""
    async def _create_classification(
        comment_id: str,
        classification: str = "question / inquiry",
        confidence: int = 95,
        **kwargs
    ) -> CommentClassification:
        clf = CommentClassification(
            comment_id=comment_id,
            type=classification,
            confidence=confidence,
            reasoning=kwargs.get("reasoning", "Test reasoning"),
            retry_count=kwargs.get("retry_count", 0),
            max_retries=kwargs.get("max_retries", 5),
            input_tokens=kwargs.get("input_tokens", 100),
            output_tokens=kwargs.get("output_tokens", 50),
            processing_status=kwargs.get("processing_status", ProcessingStatus.COMPLETED),
        )
        db_session.add(clf)
        await db_session.commit()
        await db_session.refresh(clf)
        return clf

    return _create_classification


@pytest.fixture
def answer_factory(db_session):
    """Factory for creating test answers."""
    async def _create_answer(
        comment_id: str,
        answer_text: str = None,
        **kwargs
    ) -> QuestionAnswer:
        answer = QuestionAnswer(
            comment_id=comment_id,
            answer=answer_text or fake.text(),
            answer_confidence=kwargs.get("confidence", 0.9),
            answer_quality_score=kwargs.get("quality_score", 85),
            processing_time_ms=kwargs.get("processing_time_ms", 1500),
            input_tokens=kwargs.get("input_tokens", 200),
            output_tokens=kwargs.get("output_tokens", 150),
            processing_status=kwargs.get("processing_status", AnswerStatus.COMPLETED),
            max_retries=kwargs.get("max_retries", 5),
            reply_id=kwargs.get("reply_id"),
            reply_sent=kwargs.get("reply_sent", False),
            is_deleted=kwargs.get("is_deleted", False),
        )
        db_session.add(answer)
        await db_session.commit()
        await db_session.refresh(answer)
        return answer

    return _create_answer


@pytest.fixture
def document_factory(db_session):
    """Factory for creating test documents."""
    async def _create_document(
        document_id = None,
        filename: str = None,
        document_type: str = "pdf",
        s3_url: str = None,
        processing_status: str = "completed",
        **kwargs
    ) -> Document:
        import uuid
        doc_name = filename or fake.file_name(extension=document_type)
        s3_key = f"documents/{doc_name}"

        if document_id is None:
            doc_id = uuid.uuid4()
        elif isinstance(document_id, uuid.UUID):
            doc_id = document_id
        else:
            doc_id = uuid.UUID(str(document_id))

        document = Document(
            id=doc_id,
            document_name=doc_name,
            document_type=document_type,
            s3_bucket=kwargs.get("s3_bucket", "test-bucket"),
            s3_key=s3_key,
            s3_url=s3_url or f"s3://test-bucket/{s3_key}",
            processing_status=processing_status,
            markdown_content=kwargs.get("markdown_content"),
            content_hash=kwargs.get("content_hash", fake.sha256()),
            processing_error=kwargs.get("processing_error"),
            processed_at=kwargs.get("processed_at"),
        )
        db_session.add(document)
        await db_session.commit()
        await db_session.refresh(document)
        return document

    return _create_document


@pytest.fixture
def product_embedding_factory(db_session):
    """Factory for creating test product embeddings."""
    async def _create_product_embedding(
        product_id: int = None,
        title: str = None,
        description: str = None,
        category: str = "personal_care",
        price: str = "100",
        embedding: list = None,
        **kwargs
    ) -> ProductEmbedding:
        # Default embedding vector (1536 dimensions for text-embedding-3-small)
        if embedding is None:
            embedding = [0.1] * 1536

        product_data = {
            "title": title or fake.catch_phrase(),
            "description": description or fake.text(max_nb_chars=200),
            "category": category,
            "price": price,
            "tags": kwargs.get("tags"),
            "url": kwargs.get("url", fake.url()),
            "image_url": kwargs.get("image_url", fake.image_url()),
            "embedding": embedding,
            "is_active": kwargs.get("is_active", True),
            "created_at": kwargs.get("created_at", datetime.now(timezone.utc)),
        }

        if product_id is not None:
            product_data["id"] = product_id

        product = ProductEmbedding(**product_data)
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)
        return product

    return _create_product_embedding


# ============================================================================
# CONVENIENCE ALIASES
# ============================================================================


@pytest.fixture
def comment_factory(instagram_comment_factory):
    """Alias for instagram_comment_factory for shorter test code."""
    return instagram_comment_factory


# ============================================================================
# API CLIENT FIXTURES
# ============================================================================


@pytest.fixture
def test_client() -> TestClient:
    """Sync FastAPI test client for testing endpoints."""
    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async FastAPI test client for testing async endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================================
# DEPENDENCY INJECTION FIXTURES
# ============================================================================


@pytest.fixture
def test_container():
    """Create a test DI container with mocked dependencies."""
    reset_container()
    container = Container()

    # Override with test configuration if needed
    # container.config.from_dict({"test_mode": True})

    yield container

    reset_container()


@pytest.fixture
def override_get_container(test_container):
    """Override the get_container dependency."""
    def _get_test_container():
        return test_container

    app.dependency_overrides[get_container] = _get_test_container
    yield
    app.dependency_overrides.clear()


# ============================================================================
# MOCK SERVICE FIXTURES
# ============================================================================


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test AI response"
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150
    return mock_response


@pytest.fixture
def mock_instagram_api():
    """Mock Instagram Graph API responses."""
    with patch("core.services.instagram_service.InstagramGraphAPIService") as mock:
        instance = mock.return_value
        instance.post_reply = AsyncMock(return_value={"id": "reply_123"})
        instance.hide_comment = AsyncMock(return_value={"success": True})
        instance.get_media = AsyncMock(return_value={
            "id": "media_123",
            "media_type": "IMAGE",
            "media_url": "https://example.com/image.jpg",
            "caption": "Test caption"
        })
        yield instance


@pytest.fixture
def mock_telegram_api():
    """Mock Telegram API responses."""
    with patch("core.services.telegram_alert_service.TelegramAlertService") as mock:
        instance = mock.return_value
        instance.send_alert = AsyncMock(return_value={"ok": True, "result": {"message_id": 123}})
        yield instance


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service for vector search."""
    with patch("core.services.embedding_service.EmbeddingService") as mock:
        instance = mock.return_value
        instance.search_similar_products = AsyncMock(return_value=[
            {
                "title": "Test Product",
                "description": "Test description",
                "similarity": 0.95,
                "price": "100 @C1",
                "is_ood": False,
            }
        ])
        instance.create_embedding = AsyncMock(return_value=[0.1] * 1536)
        yield instance


@pytest.fixture
def mock_s3_service():
    """Mock S3 service for file storage."""
    with patch("core.services.s3_service.S3Service") as mock:
        instance = mock.return_value
        instance.upload_file = AsyncMock(return_value="s3://bucket/file.pdf")
        instance.download_file = AsyncMock(return_value=b"file content")
        instance.delete_file = AsyncMock(return_value=True)
        yield instance


@pytest.fixture
def mock_celery_task_queue():
    """Mock Celery task queue."""
    with patch("core.infrastructure.task_queue.CeleryTaskQueue") as mock:
        instance = mock.return_value
        instance.enqueue = MagicMock(return_value="task_123")
        yield instance


# ============================================================================
# AGENT TOOL FIXTURES
# ============================================================================


@pytest.fixture
def mock_agent_runner():
    """Mock OpenAI Agents SDK Runner."""
    with patch("agents.Runner") as mock:
        mock_result = MagicMock()
        mock_result.final_output = "Test agent response"
        mock_result.raw_responses = [MagicMock()]
        mock_result.raw_responses[0].usage.input_tokens = 100
        mock_result.raw_responses[0].usage.output_tokens = 50

        mock.run = AsyncMock(return_value=mock_result)
        yield mock


# ============================================================================
# ENVIRONMENT FIXTURES
# ============================================================================


@pytest.fixture
def test_env_vars():
    """Set test environment variables."""
    original_env = os.environ.copy()

    test_vars = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "CELERY_BROKER_URL": "redis://localhost:6379/0",
        "OPENAI_API_KEY": "test_key",
        "INSTA_TOKEN": "test_token",
        "APP_SECRET": "test_secret",
        "DEVELOPMENT_MODE": "true",
    }

    os.environ.update(test_vars)
    yield test_vars

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


# ============================================================================
# UTILITY FIXTURES
# ============================================================================


@pytest.fixture
def sample_webhook_payload():
    """Sample Instagram webhook payload."""
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "instagram_business_account_id",
                "time": 1234567890,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment_123",
                            "media": {
                                "id": "media_123",
                                "media_product_type": "FEED"
                            },
                            "text": "!:>;L:> AB>8B 4>AB02:0?",
                            "from": {
                                "id": "user_123",
                                "username": "test_user"
                            }
                        }
                    }
                ]
            }
        ]
    }
