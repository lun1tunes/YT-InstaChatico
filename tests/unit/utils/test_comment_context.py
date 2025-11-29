import pytest

from core.utils.comment_context import (
    push_comment_context,
    get_comment_context,
    reset_comment_context,
)


def test_comment_context_push_and_get():
    token = push_comment_context(comment_id="comment-1", media_id="media-1")
    try:
        ctx = get_comment_context()
        assert ctx["comment_id"] == "comment-1"
        assert ctx["media_id"] == "media-1"
    finally:
        reset_comment_context(token)


def test_comment_context_reset():
    token = push_comment_context(comment_id="first", media_id="media-A")
    reset_comment_context(token)
    ctx = get_comment_context()
    assert ctx == {}


@pytest.mark.asyncio
async def test_comment_context_is_task_local():
    token_main = push_comment_context(comment_id="main", media_id="media-main")

    async def child_task():
        ctx = get_comment_context()
        assert ctx["comment_id"] == "child"
        assert ctx["media_id"] == "media-child"

    async def runner():
        token_child = push_comment_context(comment_id="child", media_id="media-child")
        try:
            await child_task()
        finally:
            reset_comment_context(token_child)

    try:
        await runner()
        ctx_after = get_comment_context()
        assert ctx_after["comment_id"] == "main"
        assert ctx_after["media_id"] == "media-main"
    finally:
        reset_comment_context(token_main)

