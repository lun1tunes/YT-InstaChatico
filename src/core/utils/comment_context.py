"""Context helpers for associating tool executions with comment/media ids."""

from __future__ import annotations

import contextvars
from typing import Optional

_comment_context: contextvars.ContextVar[dict[str, Optional[str]]] = contextvars.ContextVar(
    "comment_context",
    default={},
)


def push_comment_context(*, comment_id: Optional[str] = None, media_id: Optional[str] = None):
    """Set comment/media context for the current async task."""
    value = {"comment_id": comment_id, "media_id": media_id}
    return _comment_context.set(value)


def get_comment_context() -> dict[str, Optional[str]]:
    """Retrieve comment/media context for current async task."""
    return _comment_context.get({})


def reset_comment_context(token) -> None:
    """Reset context to previous value."""
    _comment_context.reset(token)
