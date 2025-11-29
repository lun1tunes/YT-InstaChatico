import pytest
from datetime import timedelta
from httpx import AsyncClient
from sqlalchemy import select

from core.models.stats_report import StatsReport
from core.models.instagram_comment import InstagramComment
from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.utils.time import now_db_utc


@pytest.mark.asyncio
async def test_instagram_insights_stats_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    instagram_service.insights_default_response = {
        "success": True,
        "data": {"data": [{"metric": "views"}]},
    }

    response = await client.get("/api/v1/stats/instagram_insights?period=last_month")

    assert response.status_code == 200
    body = response.json()
    assert body["payload"]["period"] == "last_month"
    assert len(body["payload"]["months"]) >= 1
    first_month = body["payload"]["months"][0]
    assert first_month["insights"]["engagement"]["data"][0]["metric"] == "views"

    async with session_factory() as session:
        reports = (await session.execute(select(StatsReport))).scalars().all()
        assert len(reports) >= 1


@pytest.mark.asyncio
async def test_instagram_insights_stats_failure(integration_environment):
    client: AsyncClient = integration_environment["client"]
    instagram_service = integration_environment["instagram_service"]
    instagram_service.insights_default_response = {"success": False, "error": "boom"}

    response = await client.get("/api/v1/stats/instagram_insights?period=last_month")

    assert response.status_code == 502
    body = response.json()
    assert body["meta"]["error"]["code"] == 5008
    assert body["payload"] is None


@pytest.mark.asyncio
async def test_instagram_account_insights_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    instagram_service = integration_environment["instagram_service"]
    instagram_service.account_profile_response = {
        "success": True,
        "data": {
            "username": "ichatico_app_test_acc",
            "media_count": 6,
            "followers_count": 122,
            "follows_count": 0,
            "id": "24857059897262720",
        },
    }

    response = await client.get("/api/v1/stats/account")

    assert response.status_code == 200
    body = response.json()
    assert body["payload"]["username"] == "ichatico_app_test_acc"
    assert body["payload"]["followers_count"] == 122


@pytest.mark.asyncio
async def test_instagram_account_insights_failure(integration_environment):
    client: AsyncClient = integration_environment["client"]
    instagram_service = integration_environment["instagram_service"]
    instagram_service.account_profile_response = {"success": False, "error": "fail"}

    response = await client.get("/api/v1/stats/account")

    assert response.status_code == 502
    body = response.json()
    assert body["meta"]["error"]["code"] == 5009
    assert body["payload"] is None


@pytest.mark.asyncio
async def test_instagram_account_insights_exception(integration_environment):
    client: AsyncClient = integration_environment["client"]
    instagram_service = integration_environment["instagram_service"]
    instagram_service.account_profile_error = RuntimeError("boom")

    response = await client.get("/api/v1/stats/account")

    assert response.status_code == 502
    body = response.json()
    assert body["meta"]["error"]["code"] == 5009
    assert body["payload"] is None


@pytest.mark.asyncio
async def test_instagram_moderation_stats_endpoint(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    now = now_db_utc().replace(tzinfo=None)

    async with session_factory() as session:
        comment = InstagramComment(
            id="mod-endpoint",
            media_id="media-1",
            user_id="user-1",
            username="tester",
            text="spam content",
            created_at=now,
            raw_data={},
            is_hidden=True,
            hidden_at=now,
            is_deleted=True,
            deleted_at=now + timedelta(minutes=5),
        )
        comment.hidden_by_ai = True
        comment.deleted_by_ai = True
        classification = CommentClassification(
            comment_id=comment.id,
            processing_status=ProcessingStatus.COMPLETED,
            processing_completed_at=now + timedelta(hours=1),
            type="spam / irrelevant",
        )
        session.add(comment)
        session.add(classification)
        await session.commit()

    response = await client.get("/api/v1/stats/moderation")

    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["months"]
    current_month = next(
        month for month in payload["months"] if month["month"] == now.strftime("%Y-%m")
    )
    assert current_month["summary"]["total_verified_content"] >= 1
    assert current_month["violations"]["spam_advertising"] >= 1
    assert current_month["ai_moderator"]["hidden_comments"]["ai"] >= 1
