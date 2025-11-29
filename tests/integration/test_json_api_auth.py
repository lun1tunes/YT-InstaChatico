"""Authentication and authorization tests for JSON API endpoints."""

import pytest
from httpx import AsyncClient

from core.models import CommentClassification, InstagramComment, Media, QuestionAnswer
from core.models.comment_classification import ProcessingStatus
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers


@pytest.mark.asyncio
async def test_media_list_missing_auth_header(integration_environment):
    """Test that media listing requires authentication."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media")
    assert response.status_code == 401
    data = response.json()
    assert data["meta"]["error"]["code"] == 4001


@pytest.mark.asyncio
async def test_media_list_invalid_auth_format(integration_environment):
    """Test that media listing rejects invalid auth format."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media", headers={"Authorization": "InvalidFormat"})
    assert response.status_code == 401
    data = response.json()
    assert data["meta"]["error"]["code"] == 4001


@pytest.mark.asyncio
async def test_media_list_wrong_token(integration_environment):
    """Test that media listing rejects wrong tokens."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
    data = response.json()
    assert data["meta"]["error"]["code"] == 4002


@pytest.mark.asyncio
async def test_comment_hide_unauthorized(integration_environment):
    """Test that comment visibility endpoint requires authentication."""
    client: AsyncClient = integration_environment["client"]
    response = await client.patch("/api/v1/comments/comment_123", params={"is_hidden": True})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_answer_patch_unauthorized(integration_environment):
    """Test that answer patching requires authentication."""
    client: AsyncClient = integration_environment["client"]
    response = await client.patch("/api/v1/answers/1", json={"answer": "New"})
    assert response.status_code == 401

