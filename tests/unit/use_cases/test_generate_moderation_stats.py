from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.models.instagram_comment import InstagramComment
from core.models.question_answer import QuestionAnswer, AnswerStatus
from core.repositories.moderation_stats import ModerationStatsRepository
from core.repositories.moderation_stats_report import ModerationStatsReportRepository
from core.use_cases.generate_moderation_stats import GenerateModerationStatsUseCase
from core.use_cases.generate_stats_report import StatsPeriod


def _freeze_now(monkeypatch, target_module):
    fixed_now = datetime(2025, 11, 16, 12, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(target_module, "datetime", FrozenDateTime)
    return fixed_now


def _make_comment(
    *,
    comment_id: str,
    created_at: datetime,
    is_hidden: bool = False,
    hidden_at: datetime | None = None,
    hidden_by_ai: bool = False,
    is_deleted: bool = False,
    deleted_at: datetime | None = None,
    deleted_by_ai: bool = False,
) -> InstagramComment:
    return InstagramComment(
        id=comment_id,
        media_id="media",
        user_id="user",
        username="tester",
        text="sample",
        created_at=created_at,
        raw_data={},
        is_hidden=is_hidden,
        hidden_at=hidden_at,
        hidden_by_ai=hidden_by_ai,
        is_deleted=is_deleted,
        deleted_at=deleted_at,
        deleted_by_ai=deleted_by_ai,
    )


def _make_classification(
    comment_id: str,
    idx: int,
    *,
    type_label: str | None,
    status: ProcessingStatus = ProcessingStatus.COMPLETED,
    created_at: datetime,
) -> CommentClassification:
    completed_at = created_at + timedelta(hours=2) if status == ProcessingStatus.COMPLETED else None
    return CommentClassification(
        comment_id=comment_id,
        processing_status=status,
        processing_completed_at=completed_at,
        type=type_label,
    )


@pytest.mark.asyncio
async def test_generate_moderation_stats(monkeypatch, db_session):
    from core.use_cases import generate_moderation_stats as moderation_module

    _freeze_now(monkeypatch, moderation_module)

    # October data to ensure previous month is present
    oct_comment = _make_comment(comment_id="oct", created_at=datetime(2025, 10, 5, 12, 0))
    oct_classification = _make_classification(
        "oct", 1, type_label="spam / irrelevant", created_at=oct_comment.created_at
    )

    # November data
    nov_base = datetime(2025, 11, 10, 9, 0)
    spam_comment = _make_comment(comment_id="spam", created_at=nov_base)
    spam_classification = _make_classification(
        "spam", 2, type_label="Spam / irrelevant", created_at=nov_base
    )

    adult_comment = _make_comment(comment_id="adult", created_at=nov_base + timedelta(hours=1))
    adult_classification = _make_classification(
        "adult", 3, type_label="18+ content", created_at=adult_comment.created_at
    )

    toxic_comment = _make_comment(comment_id="toxic", created_at=nov_base + timedelta(hours=2))
    toxic_classification = _make_classification(
        "toxic", 4, type_label="toxic / abusive", created_at=toxic_comment.created_at
    )

    other_comment = _make_comment(comment_id="other", created_at=nov_base + timedelta(hours=3))
    other_classification = _make_classification(
        "other", 5, type_label="Scam request", created_at=other_comment.created_at
    )

    complaint_created = _make_comment(comment_id="complaint-new", created_at=nov_base + timedelta(hours=4))
    complaint_pending = CommentClassification(
        comment_id="complaint-new",
        processing_status=ProcessingStatus.PENDING,
        type="urgent issue / complaint",
    )

    complaint_done_comment = _make_comment(comment_id="complaint-done", created_at=nov_base + timedelta(hours=5))
    complaint_done = _make_classification(
        "complaint-done",
        6,
        type_label="urgent issue / complaint",
        created_at=complaint_done_comment.created_at,
    )

    qa_ai_comment = _make_comment(comment_id="qa-ai", created_at=nov_base + timedelta(hours=6))
    qa_ai_classification = _make_classification(
        "qa-ai",
        7,
        type_label="question / inquiry",
        created_at=qa_ai_comment.created_at,
    )
    qa_ai_answer = QuestionAnswer(
        comment_id="qa-ai",
        processing_status=AnswerStatus.COMPLETED,
        answer="Auto reply",
        reply_sent=True,
        reply_sent_at=nov_base + timedelta(hours=6, minutes=30),
        is_deleted=False,
        is_ai_generated=True,
    )

    qa_manual_comment = _make_comment(comment_id="qa-manual", created_at=nov_base + timedelta(hours=7))
    qa_manual_classification = _make_classification(
        "qa-manual",
        8,
        type_label="question / inquiry",
        created_at=qa_manual_comment.created_at,
    )
    qa_manual_answer = QuestionAnswer(
        comment_id="qa-manual",
        processing_status=AnswerStatus.COMPLETED,
        answer="Manual reply",
        reply_sent=True,
        reply_sent_at=nov_base + timedelta(hours=7, minutes=15),
        is_deleted=False,
        is_ai_generated=False,
    )

    legacy_comment = _make_comment(
        comment_id="legacy",
        created_at=datetime(2025, 9, 1, 10, 0),
    )
    legacy_classification = CommentClassification(
        comment_id="legacy",
        processing_status=ProcessingStatus.COMPLETED,
        processing_completed_at=datetime(2025, 11, 12, 10, 0),
        type="spam / irrelevant",
    )

    hidden_comment = _make_comment(
        comment_id="hidden",
        created_at=nov_base,
        is_hidden=True,
        hidden_at=datetime(2025, 11, 12, 8, 0),
        hidden_by_ai=True,
    )
    hidden_classification = _make_classification(
        "hidden", 7, type_label="spam / irrelevant", created_at=hidden_comment.created_at
    )

    deleted_comment = _make_comment(
        comment_id="deleted",
        created_at=nov_base,
        is_deleted=True,
        deleted_at=datetime(2025, 11, 13, 9, 0),
        deleted_by_ai=True,
    )
    deleted_classification = _make_classification(
        "deleted", 8, type_label="spam / irrelevant", created_at=deleted_comment.created_at
    )

    db_session.add_all(
        [
            oct_comment,
            spam_comment,
            adult_comment,
            toxic_comment,
            other_comment,
            complaint_created,
            complaint_done_comment,
            qa_ai_comment,
            qa_manual_comment,
            hidden_comment,
            deleted_comment,
            legacy_comment,
        ]
    )
    db_session.add_all(
        [
            oct_classification,
            spam_classification,
            adult_classification,
            toxic_classification,
            other_classification,
            complaint_pending,
            complaint_done,
            qa_ai_classification,
            qa_manual_classification,
            hidden_classification,
            deleted_classification,
            qa_ai_answer,
            qa_manual_answer,
            legacy_classification,
        ]
    )
    await db_session.commit()

    use_case = GenerateModerationStatsUseCase(
        session=db_session,
        moderation_stats_repository_factory=lambda session: ModerationStatsRepository(session),
        moderation_stats_report_repository_factory=lambda session: ModerationStatsReportRepository(session),
    )

    result = await use_case.execute(StatsPeriod.LAST_MONTH)
    assert result["period"] == StatsPeriod.LAST_MONTH.value
    assert len(result["months"]) == 2

    november_stats = next(item for item in result["months"] if item["month"] == "2025-11")
    summary = november_stats["summary"]
    assert summary["total_verified_content"] == 10
    assert summary["complaints_total"] == 2
    assert summary["complaints_processed"] == 1
    assert summary["average_reaction_time_seconds"] == pytest.approx(6525.0)

    violations = november_stats["violations"]
    assert violations["spam_advertising"] == 4
    assert violations["adult_content"] == 1
    assert violations["insults_toxicity"] == 1
    assert violations["other"]["count"] == 1
    assert violations["other"]["examples"] == ["Scam request"]

    ai_stats = november_stats["ai_moderator"]
    assert ai_stats["hidden_comments"]["ai"] == 1
    assert ai_stats["hidden_comments"]["manual"] == 0
    assert ai_stats["deleted_content"]["ai"] == 1
    assert ai_stats["deleted_content"]["manual"] == 0
