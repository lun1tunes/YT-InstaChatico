"""Serialization helpers for the JSON API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from api_v1.comments.schemas import (
    AnswerDTO,
    AnswerListResponse,
    AnswerResponse,
    ClassificationDTO,
    CommentDTO,
    CommentListResponse,
    CommentResponse,
    EmptyResponse,
    ErrorDetail,
    ErrorResponse,
    MediaDTO,
    MediaQuickStats,
    MediaListResponse,
    MediaResponse,
    PaginationMeta,
    SimpleMeta,
)
from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.models.instagram_comment import InstagramComment
from core.models.media import Media
from core.models.question_answer import AnswerStatus, QuestionAnswer

MEDIA_TYPE_CODES: dict[str, int] = {
    "IMAGE": 1,
    "VIDEO": 2,
    "CAROUSEL_ALBUM": 3,
}

CLASSIFICATION_TYPE_CODES: dict[str, int] = {
    "positive feedback": 1,
    "critical feedback": 2,
    "urgent issue / complaint": 3,
    "question / inquiry": 4,
    "partnership proposal": 5,
    "toxic / abusive": 6,
    "spam / irrelevant": 7,
}

CLASSIFICATION_CODE_TO_TYPE = {code: label for label, code in CLASSIFICATION_TYPE_CODES.items()}

PROCESSING_STATUS_CODES: dict[ProcessingStatus, int] = {
    ProcessingStatus.PENDING: 1,
    ProcessingStatus.PROCESSING: 2,
    ProcessingStatus.COMPLETED: 3,
    ProcessingStatus.FAILED: 4,
    ProcessingStatus.RETRY: 5,
}

PROCESSING_STATUS_CODE_TO_ENUM = {code: status for status, code in PROCESSING_STATUS_CODES.items()}

ANSWER_STATUS_CODES: dict[AnswerStatus, int] = {
    AnswerStatus.PENDING: 1,
    AnswerStatus.PROCESSING: 2,
    AnswerStatus.COMPLETED: 3,
    AnswerStatus.FAILED: 4,
    AnswerStatus.RETRY: 5,
}

ANSWER_STATUS_CODE_TO_ENUM = {code: status for status, code in ANSWER_STATUS_CODES.items()}


def format_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def classification_type_to_code(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    return CLASSIFICATION_TYPE_CODES.get(value.lower())


def normalize_classification_label(value: str) -> Optional[str]:
    raw = value.strip()
    if not raw:
        return None
    label = raw.lower()
    if label in CLASSIFICATION_TYPE_CODES:
        return label
    if raw.isdigit():
        code = int(raw)
        mapped = CLASSIFICATION_CODE_TO_TYPE.get(code)
        return mapped.lower() if mapped else None
    return None


def classification_code_to_label(code: int) -> Optional[str]:
    return CLASSIFICATION_CODE_TO_TYPE.get(code)


def processing_status_code_to_enum(code: int) -> Optional[ProcessingStatus]:
    return PROCESSING_STATUS_CODE_TO_ENUM.get(code)


def serialize_media(media: Media, stats: Optional[MediaQuickStats] = None) -> MediaDTO:
    media_type = (media.media_type or "").upper()
    type_code = MEDIA_TYPE_CODES.get(media_type)
    children = media.children_media_urls or []
    return MediaDTO(
        id=media.id,
        permalink=media.permalink,
        caption=media.caption,
        url=media.media_url,
        type=type_code,
        context=media.media_context,
        children_urls=children,
        comments_count=media.comments_count,
        like_count=media.like_count,
        shortcode=media.shortcode,
        posted_at=format_datetime(media.posted_at) if media.posted_at else None,
        is_comment_enabled=media.is_comment_enabled,
        is_processing_enabled=bool(media.is_processing_enabled),
        stats=stats,
    )


def serialize_classification(classification: Optional[CommentClassification]) -> Optional[ClassificationDTO]:
    if not classification:
        return None
    return ClassificationDTO(
        id=classification.id,
        processing_status=PROCESSING_STATUS_CODES.get(classification.processing_status),
        processing_completed_at=format_datetime(classification.processing_completed_at),
        last_error=classification.last_error,
        confidence=classification.confidence,
        classification_type=classification_type_to_code(classification.type),
        reasoning=classification.reasoning,
    )


def serialize_answer(answer: QuestionAnswer) -> AnswerDTO:
    confidence_int: Optional[int] = None
    if answer.answer_confidence is not None:
        confidence_int = int(round(answer.answer_confidence * 100))

    return AnswerDTO(
        id=answer.id,
        processing_status=ANSWER_STATUS_CODES.get(answer.processing_status),
        processing_completed_at=format_datetime(answer.processing_completed_at),
        last_error=answer.last_error,
        answer=answer.answer,
        confidence=confidence_int,
        quality_score=answer.answer_quality_score,
        reply_sent=answer.reply_sent,
        reply_status=answer.reply_status,
        reply_error=answer.reply_error,
        is_ai_generated=bool(getattr(answer, "is_ai_generated", True)),
        is_deleted=bool(getattr(answer, "is_deleted", False)),
    )


def serialize_comment(comment: InstagramComment) -> CommentDTO:
    classification = serialize_classification(comment.classification)
    answers = []
    if comment.question_answer:
        answers.append(serialize_answer(comment.question_answer))

    last_error = None
    if comment.classification and comment.classification.last_error:
        last_error = comment.classification.last_error
    elif comment.question_answer and comment.question_answer.last_error:
        last_error = comment.question_answer.last_error

    is_deleted = getattr(comment, "is_deleted", False)
    if is_deleted is None:
        is_deleted = False

    return CommentDTO(
        id=comment.id,
        media_id=comment.media_id,
        parent_id=comment.parent_id,
        username=comment.username,
        text=comment.text,
        created_at=format_datetime(comment.created_at),
        is_hidden=comment.is_hidden,
        is_deleted=is_deleted,
        last_error=last_error,
        classification=classification,
        answers=answers,
    )


def parse_status_filters(values: Optional[List[int]]) -> Optional[List[ProcessingStatus]]:
    if not values:
        return None
    statuses: List[ProcessingStatus] = []
    for code in values:
        status = processing_status_code_to_enum(code)
        if not status:
            return None
        statuses.append(status)
    return statuses


def parse_classification_filters(values: Optional[List[int]]) -> Optional[List[str]]:
    if not values:
        return None
    labels: List[str] = []
    for code in values:
        label = classification_code_to_label(code)
        if not label:
            return None
        labels.append(label)
    return labels


def list_classification_types() -> List[tuple[int, str]]:
    """Return classification type options as (code, label) pairs sorted by code."""
    pairs = [(code, label) for label, code in CLASSIFICATION_TYPE_CODES.items()]
    return sorted(pairs, key=lambda item: item[0])
