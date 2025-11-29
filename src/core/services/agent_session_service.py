"""
Agent session service backed by SQLiteSession from OpenAI Agents SDK.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import List

from agents import SQLiteSession

from core.interfaces.agents import IAgentSession, IAgentSessionService


class AgentSessionService(IAgentSessionService):
    """Manage agent sessions stored in SQLite for conversation continuity."""

    def __init__(self, db_path: str = "conversations/conversations.db"):
        self.db_path = db_path
        self._ensure_db_directory()

    def _ensure_db_directory(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_session(self, conversation_id: str) -> IAgentSession:
        return SQLiteSession(conversation_id, self.db_path)

    async def has_messages(self, conversation_id: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._session_has_messages_sync, conversation_id)

    def _session_has_messages_sync(self, conversation_id: str) -> bool:
        db_path = Path(self.db_path)
        if not db_path.exists():
            return False

        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM agent_messages WHERE session_id = ?",
                (conversation_id,),
            )
            count = cursor.fetchone()[0]
            return count > 0

    async def ensure_context(self, conversation_id: str, context_items: List[dict]) -> IAgentSession:
        session = self.get_session(conversation_id)

        if context_items and not await self.has_messages(conversation_id):
            await session.add_items(context_items)

        return session
