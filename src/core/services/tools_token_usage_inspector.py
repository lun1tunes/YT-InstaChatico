"""Utility to persist OpenAI tool token usage information."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..repositories.instrument_token_usage import InstrumentTokenUsageRepository

logger = logging.getLogger(__name__)


class ToolsTokenUsageInspector:
    """
    Records token usage for auxiliary tools (classification agent, embedding search, vision, etc.).

    Designed to accept an optional externally managed session. If no session is provided,
    the inspector will open a short-lived session using the injected session factory.
    """

    def __init__(
        self,
        session: Optional[AsyncSession],
        repository_factory: Callable[..., InstrumentTokenUsageRepository],
        session_factory: Callable[[], async_sessionmaker[AsyncSession]],
    ):
        self._session = session
        self._repository_factory = repository_factory
        self._session_factory_provider = session_factory

    async def record(
        self,
        *,
        tool: str,
        task: str,
        model: Optional[str] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        comment_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        comment_ref = comment_id
        if comment_ref and comment_ref.startswith("first_question_comment_"):
            comment_ref = comment_ref.split("_", 3)[-1]

        async def _persist(session: AsyncSession) -> None:
            repo = self._repository_factory(session=session)
            logger.info(
                "Recording tool usage | tool=%s | task=%s | model=%s | comment_id=%s",
                tool,
                task,
                model,
                comment_ref,
            )
            await repo.log(
                tool=tool,
                task=task,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                comment_id=comment_ref,
                details={
                    **(metadata or {}),
                    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                },
            )

        if self._session is not None:
            await _persist(self._session)
        else:
            session_factory = self._session_factory_provider()
            async with session_factory() as temp_session:
                await _persist(temp_session)
                try:
                    await temp_session.commit()
                except Exception:
                    logger.exception("Failed to commit tools token usage entry")
                    await temp_session.rollback()
