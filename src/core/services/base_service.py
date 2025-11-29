"""Base service class with common functionality."""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentSession, IAgentSessionService

logger = logging.getLogger(__name__)


class BaseService:
    """Base class providing common service functionality."""

    def __init__(
        self,
        db_path: str = "conversations/conversations.db",
        session_service: Optional["IAgentSessionService"] = None,
    ):
        self.db_path = db_path
        self._ensure_db_directory()
        if session_service is None:
            # Lazily import to avoid circular dependencies when used in testing utilities.
            from core.services.agent_session_service import AgentSessionService

            self.session_service: IAgentSessionService = AgentSessionService(db_path)
        else:
            self.session_service = session_service

    def _ensure_db_directory(self):
        """Create database directory if needed."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_input(text: str) -> str:
        """Sanitize text: escape HTML, normalize whitespace, limit punctuation."""
        sanitized = html.escape(text)
        sanitized = " ".join(sanitized.split())
        sanitized = re.sub(r"([!?.]){3,}", r"\1\1\1", sanitized)
        return sanitized

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count (~4 chars per token)."""
        return len(text) // 4

    def _get_session(self, conversation_id: str) -> "IAgentSession":
        """Retrieve session with conversation history."""
        logger.debug(f"Retrieving session for conversation: {conversation_id}")
        return self.session_service.get_session(conversation_id)

    async def _session_has_messages(self, conversation_id: str) -> bool:
        """Check if session has existing messages in database."""
        try:
            return await self.session_service.has_messages(conversation_id)
        except Exception as e:
            logger.warning(f"Error checking session: {e}")
            return False
