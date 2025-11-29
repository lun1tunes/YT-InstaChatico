"""
Repository protocol definitions to decouple use cases from SQLAlchemy concrete implementations.
"""

from __future__ import annotations

from typing import Iterable, Optional, Protocol, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from core.models.instagram_comment import InstagramComment
    from core.models.comment_classification import CommentClassification
    from core.models.question_answer import QuestionAnswer
    from core.models.media import Media
    from core.models.document import Document
    from core.models.stats_report import StatsReport
    from core.models.followers_dynamic import FollowersDynamic


class ICommentRepository(Protocol):
    async def get_by_id(self, comment_id: str) -> Optional["InstagramComment"]:
        ...

    async def mark_deleted_with_descendants(self, comment_id: str) -> int:
        ...

    async def get_with_classification(self, comment_id: str) -> Optional["InstagramComment"]:
        ...

    async def get_with_answer(self, comment_id: str) -> Optional["InstagramComment"]:
        ...

    async def get_full(self, comment_id: str) -> Optional["InstagramComment"]:
        ...


class IClassificationRepository(Protocol):
    async def get_by_comment_id(self, comment_id: str) -> Optional["CommentClassification"]:
        ...

    async def get_pending_retries(self) -> Iterable["CommentClassification"]:
        ...

    async def create(self, entity: "CommentClassification") -> "CommentClassification":
        ...

    async def mark_processing(self, classification: "CommentClassification", retry_count: int = 0) -> None:
        ...

    async def mark_completed(self, classification: "CommentClassification") -> None:
        ...

    async def mark_failed(self, classification: "CommentClassification", error: str) -> None:
        ...


class IAnswerRepository(Protocol):
    async def get_by_comment_id(self, comment_id: str) -> Optional["QuestionAnswer"]:
        ...

    async def get_by_reply_id(self, reply_id: str) -> Optional["QuestionAnswer"]:
        ...

    async def create_for_comment(self, comment_id: str) -> "QuestionAnswer":
        ...


class IMediaRepository(Protocol):
    async def get_by_id(self, media_id: str) -> Optional["Media"]:
        ...

    async def exists_by_id(self, media_id: str) -> bool:
        ...

    async def create(self, entity: "Media") -> "Media":
        ...

    async def get_with_comments(self, media_id: str) -> Optional["Media"]:
        ...

    async def get_media_needing_analysis(self, limit: int = 10) -> Iterable["Media"]:
        ...


class IDocumentRepository(Protocol):
    async def get_by_id(self, document_id: str | UUID) -> Optional["Document"]:
        ...


class IStatsReportRepository(Protocol):
    async def get_by_range(self, range_start, range_end) -> "StatsReport" | None:
        ...


class IModerationStatsRepository(Protocol):
    async def gather_metrics(self, range_start, range_end) -> dict:
        ...


class IModerationStatsReportRepository(Protocol):
    async def get_by_range(self, range_start, range_end):
        ...

    async def save_month_report(
        self,
        *,
        period_label: str,
        range_start,
        range_end,
        payload: dict,
    ):
        ...


class IFollowersDynamicRepository(Protocol):
    async def get_by_snapshot_date(self, snapshot_date) -> Optional["FollowersDynamic"]:
        ...

    async def upsert_snapshot(
        self,
        *,
        snapshot_date,
        username: str | None,
        followers_count: int,
        follows_count: int | None,
        media_count: int | None,
        raw_payload: dict,
    ) -> "FollowersDynamic":
        ...

    async def save_month_report(
        self,
        *,
        period_label: str,
        range_start,
        range_end,
        payload: dict,
    ) -> "StatsReport":
        ...

    async def get_completed_with_content(self) -> Iterable["Document"]:
        ...

    async def get_summary_stats(self) -> dict:
        ...

    async def mark_processing(self, document: "Document") -> None:
        ...

    async def mark_completed(self, document: "Document", markdown_content: str) -> None:
        ...

    async def mark_failed(self, document: "Document", error: str) -> None:
        ...
