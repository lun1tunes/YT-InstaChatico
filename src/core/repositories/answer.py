"""Answer repository for data access layer."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.question_answer import QuestionAnswer, AnswerStatus


class AnswerRepository(BaseRepository[QuestionAnswer]):
    """Repository for QuestionAnswer operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(QuestionAnswer, session)

    async def get_by_comment_id(self, comment_id: str) -> Optional[QuestionAnswer]:
        """Get answer by comment ID."""
        result = await self.session.execute(
            select(QuestionAnswer).where(
                QuestionAnswer.comment_id == comment_id,
                QuestionAnswer.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, answer_id: int) -> Optional[QuestionAnswer]:
        """Get answer row with a write lock (FOR UPDATE) to coordinate concurrent mutations."""
        stmt = (
            select(QuestionAnswer)
            .where(
                QuestionAnswer.id == answer_id,
                QuestionAnswer.is_deleted.is_(False),
            )
            .with_for_update()
        )
        try:
            result = await self.session.execute(stmt)
        except NotImplementedError:
            # Dialects like SQLite do not support FOR UPDATE; fall back to a plain select.
            fallback_stmt = select(QuestionAnswer).where(
                QuestionAnswer.id == answer_id,
                QuestionAnswer.is_deleted.is_(False),
            )
            result = await self.session.execute(fallback_stmt)
        return result.scalar_one_or_none()

    async def get_by_reply_id(self, reply_id: str) -> Optional[QuestionAnswer]:
        """Get answer by Instagram reply ID (for bot loop detection)."""
        result = await self.session.execute(
            select(QuestionAnswer).where(
                QuestionAnswer.reply_id == reply_id,
                QuestionAnswer.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_for_comment(self, comment_id: str) -> QuestionAnswer:
        """Create a new answer record for a comment."""
        answer = QuestionAnswer(
            comment_id=comment_id,
            processing_status=AnswerStatus.PENDING,
            is_deleted=False,
        )
        self.session.add(answer)
        await self.session.flush()
        return answer

    async def get_pending_answers(self, limit: int = 10) -> list[QuestionAnswer]:
        """Get pending answers for processing."""
        result = await self.session.execute(
            select(QuestionAnswer)
            .where(
                QuestionAnswer.processing_status == AnswerStatus.PENDING,
                QuestionAnswer.is_deleted.is_(False),
            )
            .limit(limit)
        )
        return list(result.scalars().all())
