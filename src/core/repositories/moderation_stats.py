from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.instagram_comment import InstagramComment
from ..models.comment_classification import CommentClassification, ProcessingStatus
from ..models.question_answer import QuestionAnswer, AnswerStatus


COMPLAINT_LABEL = "urgent issue / complaint"
QUESTION_LABEL = "question / inquiry"


class ModerationStatsRepository:
    """Repository responsible for aggregating moderation metrics."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def gather_metrics(self, range_start: datetime, range_end: datetime) -> dict[str, Any]:
        summary = await self._build_summary(range_start, range_end)
        violations = await self._build_violation_breakdown(range_start, range_end)
        ai_moderator = await self._build_ai_moderator_stats(range_start, range_end)
        return {
            "summary": summary,
            "violations": violations,
            "ai_moderator": ai_moderator,
        }

    async def _build_summary(self, range_start: datetime, range_end: datetime) -> dict[str, Any]:
        total_verified = await self._count_verified(range_start, range_end)
        complaints_total = await self._count_complaints(range_start, range_end, processed_only=False)
        complaints_processed = await self._count_complaints(range_start, range_end, processed_only=True)
        reaction_time = await self._average_reaction_time(range_start, range_end)

        return {
            "total_verified_content": total_verified,
            "complaints_total": complaints_total,
            "complaints_processed": complaints_processed,
            "average_reaction_time_seconds": reaction_time,
        }

    async def _build_violation_breakdown(self, range_start: datetime, range_end: datetime) -> dict[str, Any]:
        stmt = (
            select(CommentClassification.type, func.count().label("count"))
            .join(InstagramComment, InstagramComment.id == CommentClassification.comment_id)
            .where(
                CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                CommentClassification.processing_completed_at.isnot(None),
                CommentClassification.processing_completed_at >= range_start,
                CommentClassification.processing_completed_at < range_end,
            )
            .group_by(CommentClassification.type)
        )
        result = await self.session.execute(stmt)
        category_counts = defaultdict(int)
        other_examples: list[str] = []

        for label, count in result.all():
            normalized_label = (label or "").strip().lower()
            if normalized_label in {COMPLAINT_LABEL, QUESTION_LABEL}:
                continue
            category = _categorize_violation(label)
            category_counts[category] += count or 0
            if category == "other" and label:
                normalized = label.strip()
                if normalized and normalized not in other_examples:
                    other_examples.append(normalized)

        return {
            "spam_advertising": category_counts["spam_advertising"],
            "adult_content": category_counts["adult_content"],
            "insults_toxicity": category_counts["insults_toxicity"],
            "other": {
                "count": category_counts["other"],
                "examples": other_examples[:3],
            },
        }

    async def _build_ai_moderator_stats(self, range_start: datetime, range_end: datetime) -> dict[str, Any]:
        deleted_ai = await self._count_deletions(range_start, range_end, ai_only=True)
        deleted_manual = await self._count_deletions(range_start, range_end, ai_only=False)
        hidden_ai = await self._count_hidden(range_start, range_end, ai_only=True)
        hidden_manual = await self._count_hidden(range_start, range_end, ai_only=False)

        return {
            "deleted_content": {"ai": deleted_ai, "manual": deleted_manual},
            "hidden_comments": {"ai": hidden_ai, "manual": hidden_manual},
        }

    async def _count_deletions(self, range_start: datetime, range_end: datetime, ai_only: bool) -> int:
        stmt = select(func.count()).where(
            InstagramComment.deleted_at.isnot(None),
            InstagramComment.deleted_at >= range_start,
            InstagramComment.deleted_at < range_end,
            InstagramComment.deleted_by_ai.is_(ai_only),
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _count_hidden(self, range_start: datetime, range_end: datetime, ai_only: bool) -> int:
        stmt = select(func.count()).where(
            InstagramComment.hidden_at.isnot(None),
            InstagramComment.hidden_at >= range_start,
            InstagramComment.hidden_at < range_end,
            InstagramComment.hidden_by_ai.is_(ai_only),
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _count_verified(self, range_start: datetime, range_end: datetime) -> int:
        stmt = select(func.count()).where(
            CommentClassification.processing_status == ProcessingStatus.COMPLETED,
            CommentClassification.processing_completed_at.isnot(None),
            CommentClassification.processing_completed_at >= range_start,
            CommentClassification.processing_completed_at < range_end,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _count_complaints(self, range_start: datetime, range_end: datetime, *, processed_only: bool) -> int:
        stmt = (
            select(func.count())
            .select_from(CommentClassification)
            .join(InstagramComment, InstagramComment.id == CommentClassification.comment_id)
            .where(
                CommentClassification.type.isnot(None),
                func.lower(CommentClassification.type) == COMPLAINT_LABEL,
            )
        )

        if processed_only:
            stmt = stmt.where(
                CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                CommentClassification.processing_completed_at.isnot(None),
                CommentClassification.processing_completed_at >= range_start,
                CommentClassification.processing_completed_at < range_end,
            )
        else:
            stmt = stmt.where(
                InstagramComment.created_at >= range_start,
                InstagramComment.created_at < range_end,
            )

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _average_reaction_time(self, range_start: datetime, range_end: datetime) -> float | None:
        durations: list[float] = []
        durations.extend(await self._answer_reaction_durations(range_start, range_end))
        durations.extend(await self._classification_reaction_durations(range_start, range_end))
        if not durations:
            return None
        return sum(durations) / len(durations)

    async def _answer_reaction_durations(self, range_start: datetime, range_end: datetime) -> list[float]:
        stmt = (
            select(
                InstagramComment.created_at,
                QuestionAnswer.reply_sent_at,
                QuestionAnswer.is_ai_generated,
            )
            .join(QuestionAnswer, QuestionAnswer.comment_id == InstagramComment.id)
            .join(CommentClassification, CommentClassification.comment_id == InstagramComment.id)
            .where(
                QuestionAnswer.reply_sent.is_(True),
                QuestionAnswer.reply_sent_at.isnot(None),
                QuestionAnswer.is_deleted.is_(False),
                QuestionAnswer.processing_status == AnswerStatus.COMPLETED,
                QuestionAnswer.is_ai_generated.is_(True),
                QuestionAnswer.reply_sent_at >= range_start,
                QuestionAnswer.reply_sent_at < range_end,
                InstagramComment.created_at >= range_start,
                InstagramComment.created_at < range_end,
                func.lower(CommentClassification.type) == QUESTION_LABEL,
            )
        )
        rows = await self.session.execute(stmt)
        durations: list[float] = []
        for created_at, reply_sent_at, _ in rows.all():
            if not created_at or not reply_sent_at:
                continue
            seconds = (reply_sent_at - created_at).total_seconds()
            if 0 <= seconds <= _MAX_REACTION_SECONDS:
                durations.append(seconds)
        return durations

    async def _classification_reaction_durations(self, range_start: datetime, range_end: datetime) -> list[float]:
        stmt = (
            select(
                InstagramComment.created_at,
                CommentClassification.processing_completed_at,
            )
            .join(InstagramComment, InstagramComment.id == CommentClassification.comment_id)
            .where(
                CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                CommentClassification.processing_completed_at.isnot(None),
                CommentClassification.processing_completed_at >= range_start,
                CommentClassification.processing_completed_at < range_end,
                InstagramComment.created_at >= range_start,
                InstagramComment.created_at < range_end,
                func.coalesce(func.lower(CommentClassification.type), "") != QUESTION_LABEL,
            )
        )
        rows = await self.session.execute(stmt)
        durations: list[float] = []
        for created_at, completed_at in rows.all():
            if created_at and completed_at:
                seconds = (completed_at - created_at).total_seconds()
                if 0 <= seconds <= _MAX_REACTION_SECONDS:
                    durations.append(seconds)
        return durations


def _categorize_violation(label: str | None) -> str:
    normalized = (label or "").strip().lower()
    if not normalized:
        return "other"
    if "spam" in normalized or "advert" in normalized:
        return "spam_advertising"
    if "18" in normalized or "adult" in normalized or "nsfw" in normalized:
        return "adult_content"
    if "toxic" in normalized or "abusive" in normalized or "insult" in normalized or "harass" in normalized:
        return "insults_toxicity"
    return "other"
_MAX_REACTION_SECONDS = 6 * 60 * 60  # cap outliers at 6 hours to avoid skew
