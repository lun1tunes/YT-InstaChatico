"""Unit tests for comment webhook helper functions."""

from datetime import datetime

import pytest

from api_v1.comment_webhooks import helpers
from api_v1.comment_webhooks.schemas import CommentAuthor, CommentMedia, CommentValue
from core.config import settings


class _StubAnswerRepository:
    def __init__(self, replies):
        self._replies = replies

    async def get_by_reply_id(self, reply_id):
        return self._replies.get(reply_id)


def _build_comment(**overrides) -> CommentValue:
    data = {
        "id": "comment_1",
        "media": CommentMedia(id="media_1"),
        "from_": CommentAuthor(id="author_1", username="user"),
        "parent_id": overrides.get("parent_id"),
        "text": overrides.get("text", "Hello"),
    }
    data.update(overrides)
    return CommentValue(**data)


@pytest.mark.asyncio
async def test_should_skip_comment_from_bot(monkeypatch):
    monkeypatch.setattr(settings.instagram, "bot_username", "bot_user")
    comment = _build_comment(from_=CommentAuthor(id="author", username="bot_user"))
    repo = _StubAnswerRepository({})

    should_skip, reason = await helpers.should_skip_comment(comment, repo)

    assert should_skip is True
    assert reason == "Bot reply detected (bot_user)"


@pytest.mark.asyncio
async def test_should_skip_reply_to_bot(monkeypatch):
    monkeypatch.setattr(settings.instagram, "bot_username", "brand_bot")
    comment = _build_comment(parent_id="parent_comment")
    repo = _StubAnswerRepository({"parent_comment": object()})

    should_skip, reason = await helpers.should_skip_comment(comment, repo)

    assert should_skip is True
    assert reason == "Reply to bot comment parent_comment"


@pytest.mark.asyncio
async def test_should_skip_when_own_reply(monkeypatch):
    monkeypatch.setattr(settings.instagram, "bot_username", "")
    comment = _build_comment(id="bot_reply")
    repo = _StubAnswerRepository({"bot_reply": object()})

    should_skip, reason = await helpers.should_skip_comment(comment, repo)

    assert should_skip is True
    assert reason == "Own reply detected via reply_id"


@pytest.mark.asyncio
async def test_should_not_skip_normal_comment(monkeypatch):
    monkeypatch.setattr(settings.instagram, "bot_username", "brand_bot")
    comment = _build_comment()
    repo = _StubAnswerRepository({})

    should_skip, reason = await helpers.should_skip_comment(comment, repo)

    assert should_skip is False
    assert reason == ""


def test_extract_comment_data(monkeypatch):
    comment = _build_comment(
        id="comment_x",
        media=CommentMedia(id="media_y"),
        from_=CommentAuthor(id="author_z", username="tester"),
        parent_id="parent_1",
        text="Great post",
    )
    entry_timestamp = 1_700_000_000

    data = helpers.extract_comment_data(comment, entry_timestamp)

    assert data["id"] == "comment_x"
    assert data["media_id"] == "media_y"
    assert data["user_id"] == "author_z"
    assert data["username"] == "tester"
    assert data["text"] == "Great post"
    assert data["parent_id"] == "parent_1"
    assert data["raw_data"]["id"] == "comment_x"
    assert data["created_at"] == datetime.fromtimestamp(entry_timestamp)
