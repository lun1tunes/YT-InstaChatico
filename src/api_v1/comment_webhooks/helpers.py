"""Helper functions for webhook processing."""

import logging
from typing import Optional

from core.models.instagram_comment import InstagramComment
from core.repositories.comment import CommentRepository
from core.repositories.answer import AnswerRepository
from core.config import settings

from .schemas import CommentValue

logger = logging.getLogger(__name__)


async def should_skip_comment(
    comment: CommentValue,
    answer_repo: AnswerRepository,
) -> tuple[bool, str]:
    """
    Determine if a comment should be skipped.

    Args:
        comment: The comment to check
        answer_repo: Answer repository for checking bot replies

    Returns:
        (should_skip, reason) tuple
    """
    comment_id = comment.id

    # Check 1: Is this from our bot?
    if settings.instagram.bot_username:
        if comment.is_from_user(settings.instagram.bot_username):
            return True, f"Bot reply detected ({comment.from_.username})"

    # Check 2: Is this a reply to our bot's comment?
    if comment.is_reply():
        parent_id = comment.parent_id
        parent_answer = await answer_repo.get_by_reply_id(parent_id)
        if parent_answer:
            return True, f"Reply to bot comment {parent_id}"

    # Check 3: Is this comment_id already our bot's reply?
    own_reply = await answer_repo.get_by_reply_id(comment_id)
    if own_reply:
        return True, "Own reply detected via reply_id"

    return False, ""


def extract_comment_data(comment: CommentValue, entry_timestamp: int) -> dict:
    """Extract comment data for database insertion."""
    from datetime import datetime

    return {
        "id": comment.id,
        "media_id": comment.media.id,
        "user_id": comment.from_.id,
        "username": comment.from_.username,
        "text": comment.text,
        "created_at": datetime.fromtimestamp(entry_timestamp),
        "parent_id": comment.parent_id,
        "raw_data": comment.model_dump(),
    }
