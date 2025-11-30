"""JSON API endpoints for media, comments, and answers."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, AsyncIterator, List, Optional

import jwt
from fastapi import APIRouter, Body, Depends, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from jwt import ExpiredSignatureError, InvalidTokenError
from jwt.exceptions import MissingRequiredClaimError

from core.config import settings
from core.models import db_helper
from core.repositories.answer import AnswerRepository
from core.repositories.comment import CommentRepository
from core.repositories.media import MediaRepository
from core.repositories.classification import ClassificationRepository
from core.repositories.expired_token import ExpiredTokenRepository
from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.use_cases.delete_comment import DeleteCommentUseCase
from core.use_cases.hide_comment import HideCommentUseCase
from core.dependencies import get_container
from sqlalchemy import update
from api_v1.comments.serializers import (
    AnswerListResponse,
    AnswerResponse,
    CommentListResponse,
    CommentResponse,
    EmptyResponse,
    ErrorDetail,
    ErrorResponse,
    MediaListResponse,
    MediaResponse,
    PaginationMeta,
    SimpleMeta,
    normalize_classification_label,
    parse_status_filters,
    parse_classification_filters,
    serialize_answer,
    serialize_comment,
    serialize_media,
    list_classification_types,
)
from core.utils.time import now_db_utc
from core.use_cases.proxy_media_image import MediaImageProxyError
from core.use_cases.replace_answer import ReplaceAnswerError
from core.use_cases.create_manual_answer import ManualAnswerCreateError
from .schemas import (
    AnswerCreateRequest,
    AnswerUpdateRequest,
    ClassificationUpdateRequest,
    MediaUpdateRequest,
    ClassificationTypeDTO,
    ClassificationTypesResponse,
    MediaQuickStats,
)

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

router = APIRouter(tags=["JSON API"])

MEDIA_DEFAULT_PER_PAGE = 10
MEDIA_MAX_PER_PAGE = 30
COMMENTS_DEFAULT_PER_PAGE = 30
COMMENTS_MAX_PER_PAGE = 100


JSON_API_PATH_PREFIXES = (
    f"{settings.api_v1_prefix}/media",
    f"{settings.api_v1_prefix}/comments",
    f"{settings.api_v1_prefix}/answers",
    f"{settings.api_v1_prefix}/meta",
)

QUICK_STATS_WINDOW = timedelta(hours=1)
CLASSIFICATION_STATS_KEYS = {
    "positive feedback": "positive_feedback",
    "question / inquiry": "questions",
    "critical feedback": "negative_feedback",
    "urgent issue / complaint": "urgent_issues",
    "partnership proposal": "partnership_proposals",
    "toxic / abusive": "toxic_abusive",
    "spam / irrelevant": "spam_irrelevant",
}


class JsonApiError(Exception):
    def __init__(self, status_code: int, code: int, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


# NOTE: using explicit security dependency so Swagger UI sends Authorization header
async def require_service_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
) -> dict[str, Any]:
    secret_key = settings.json_api.secret_key
    algorithm = settings.json_api.algorithm

    if not secret_key:
        raise JsonApiError(503, 5001, "JSON API secret key is not configured")
    if not credentials or credentials.scheme.lower() != "bearer":
        raise JsonApiError(401, 4001, "Missing or invalid Authorization header")

    token = credentials.credentials.strip()
    repo = ExpiredTokenRepository(session)

    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[algorithm],
            options={"require": ["exp"]},
        )
    except ExpiredSignatureError:
        payload = _decode_without_exp(token, secret_key, algorithm)
        token_id = _token_identifier(token, payload)
        await _record_expired_token(session, repo, payload, token_id)
        raise JsonApiError(401, 4005, "Token expired")
    except MissingRequiredClaimError:
        raise JsonApiError(401, 4003, "Token missing required claim")
    except InvalidTokenError:
        raise JsonApiError(401, 4002, "Unauthorized")

    token_id = _token_identifier(token, payload)

    if await repo.get_by_jti(token_id):
        raise JsonApiError(401, 4005, "Token expired")

    return payload


def _decode_without_exp(token: str, secret_key: str, algorithm: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        secret_key,
        algorithms=[algorithm],
        options={"verify_exp": False},
    )


def _token_identifier(token: str, payload: dict[str, Any]) -> str:
    raw_jti = payload.get("jti")
    if isinstance(raw_jti, str) and raw_jti.strip():
        return raw_jti.strip()
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _record_expired_token(
    session: AsyncSession,
    repo: ExpiredTokenRepository,
    payload: dict[str, Any],
    token_id: str,
) -> None:
    exp = payload.get("exp")
    if not exp:
        return

    expired_at = datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None)
    try:
        await repo.record_expired(token_id, expired_at)
        await session.commit()
    except Exception:
        await session.rollback()


def _is_json_api_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in JSON_API_PATH_PREFIXES)


async def json_api_error_handler(_: Request, exc: JsonApiError):
    error = ErrorDetail(code=exc.code, message=exc.message)
    body = ErrorResponse(meta=SimpleMeta(error=error))
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


async def validation_error_handler(request: Request, exc: RequestValidationError):
    if not _is_json_api_path(request.url.path):
        return await request_validation_exception_handler(request, exc)
    error = ErrorDetail(code=4000, message="Validation error", details=exc.errors())
    body = ErrorResponse(meta=SimpleMeta(error=error))
    return JSONResponse(status_code=422, content=body.model_dump())


async def _get_media_or_404(session: AsyncSession, media_id: str) -> Any:
    repo = MediaRepository(session)
    media = await repo.get_by_id(media_id)
    if not media:
        raise JsonApiError(404, 4040, "Media not found")
    return media


async def _get_comment_or_404(session: AsyncSession, comment_id: str) -> Any:
    repo = CommentRepository(session)
    comment = await repo.get_full(comment_id)
    if not comment:
        raise JsonApiError(404, 4041, "Comment not found")
    return comment


def _init_stats_state() -> dict[str, dict[str, int]]:
    return {key: {"total": 0, "increment": 0} for key in CLASSIFICATION_STATS_KEYS.values()}


def _state_to_quick_stats(state: dict[str, dict[str, int]]) -> MediaQuickStats:
    payload: dict[str, int] = {}
    for key, values in state.items():
        payload[f"{key}_total"] = values["total"]
        payload[f"{key}_increment"] = values["increment"]
    return MediaQuickStats(**payload)


def _apply_classification_stats(
    state: dict[str, dict[str, int]],
    classification_label: Optional[str],
    total_count: int,
    recent_count: int,
) -> None:
    if not classification_label:
        return
    normalized = classification_label.strip().lower()
    stat_key = CLASSIFICATION_STATS_KEYS.get(normalized)
    if not stat_key:
        logger.debug("Quick stats skipping unknown classification | type=%s", classification_label)
        return
    state[stat_key]["total"] = total_count
    state[stat_key]["increment"] = recent_count


async def _get_comment_quick_stats(session: AsyncSession) -> MediaQuickStats:
    """Return aggregated stats across all media for last hour + totals."""
    cutoff = now_db_utc() - QUICK_STATS_WINDOW
    repo = ClassificationRepository(session)
    rows = await repo.get_completed_stats_since(cutoff)
    stats_state = _init_stats_state()
    for cls_type, total_count, recent_count in rows:
        _apply_classification_stats(stats_state, cls_type, total_count, recent_count)
    return _state_to_quick_stats(stats_state)


async def _get_media_stats_map(session: AsyncSession, media_ids: list[str]) -> dict[str, MediaQuickStats]:
    if not media_ids:
        return {}

    cutoff = now_db_utc() - QUICK_STATS_WINDOW
    repo = ClassificationRepository(session)
    rows = await repo.get_completed_stats_since_by_media(media_ids, cutoff)

    states = {media_id: _init_stats_state() for media_id in media_ids}
    for media_id, cls_type, total_count, recent_count in rows:
        if media_id not in states:
            continue
        _apply_classification_stats(states[media_id], cls_type, total_count, recent_count)

    return {media_id: _state_to_quick_stats(state) for media_id, state in states.items()}


async def _get_answer_or_404(session: AsyncSession, answer_id: int) -> Any:
    repo = AnswerRepository(session)
    answer = await repo.get_by_id(answer_id)
    if not answer or getattr(answer, "is_deleted", False):
        raise JsonApiError(404, 4042, "Answer not found")
    return answer


async def _get_answer_for_update_or_404(session: AsyncSession, answer_id: int) -> Any:
    repo = AnswerRepository(session)
    answer = await repo.get_for_update(answer_id)
    if not answer or getattr(answer, "is_deleted", False):
        raise JsonApiError(404, 4042, "Answer not found")
    return answer


def _clamp_per_page(value: int, default: int, max_value: int) -> int:
    if value is None:
        return default
    return min(max(value, 1), max_value)


def _parse_comment_filters(
    status_multi: Optional[List[int]],
    status_csv: Optional[str],
    classification_multi: Optional[List[int]],
    classification_csv: Optional[str],
    classification_multi_alt: Optional[List[int]],
    classification_csv_alt: Optional[str],
) -> tuple[Optional[list[ProcessingStatus]], Optional[list[str]]]:
    def _append_values(target: List[int], source: Optional[List[int]]):
        if source:
            target.extend(source)

    def _append_csv(target: List[int], raw: Optional[str], error_code: int, message: str):
        if not raw:
            return
        for part in raw.split(","):
            token = part.strip()
            if not token:
                continue
            try:
                target.append(int(token))
            except ValueError:
                raise JsonApiError(400, error_code, message)

    status_values: List[int] = []
    _append_values(status_values, status_multi)
    _append_csv(status_values, status_csv, 4006, "Invalid status filter")

    statuses = parse_status_filters(status_values) if status_values else None
    if status_values and statuses is None:
        raise JsonApiError(400, 4006, "Invalid status filter")

    classification_values: List[int] = []
    _append_values(classification_values, classification_multi)
    _append_values(classification_values, classification_multi_alt)
    _append_csv(classification_values, classification_csv, 4007, "Invalid classification filter")
    _append_csv(classification_values, classification_csv_alt, 4007, "Invalid classification filter")

    classification_types = (
        parse_classification_filters(classification_values) if classification_values else None
    )
    if classification_values and classification_types is None:
        raise JsonApiError(400, 4007, "Invalid classification filter")

    return statuses, classification_types


@router.get("/media")
async def list_media(
    _: None = Depends(require_service_token),
    page: int = Query(1, ge=1),
    per_page: int = Query(MEDIA_DEFAULT_PER_PAGE, ge=1),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    per_page = _clamp_per_page(per_page, MEDIA_DEFAULT_PER_PAGE, MEDIA_MAX_PER_PAGE)
    offset = (page - 1) * per_page
    repo = MediaRepository(session)
    total = await repo.count_all()
    items = await repo.list_paginated(offset=offset, limit=per_page)
    media_ids = [media.id for media in items]
    stats_map = await _get_media_stats_map(session, media_ids)
    payload = [serialize_media(media, stats=stats_map.get(media.id)) for media in items]
    response = MediaListResponse(
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
        payload=payload,
    )
    return response


@router.get("/media/{id}")
async def get_media(
    _: None = Depends(require_service_token),
    media_id: str = Path(..., alias="id"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    media = await _get_media_or_404(session, media_id)
    stats_map = await _get_media_stats_map(session, [media.id])
    return MediaResponse(meta=SimpleMeta(), payload=serialize_media(media, stats=stats_map.get(media.id)))


@router.patch("/media/{id}")
async def patch_media(
    _: None = Depends(require_service_token),
    media_id: str = Path(..., alias="id"),
    body: MediaUpdateRequest = Body(...),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    logger.debug(
        "Patch media request received | media_id=%s | payload=%s",
        media_id,
        body.model_dump(exclude_none=True),
    )
    media = await _get_media_or_404(session, media_id)
    container = get_container()
    updated_comment_status = False

    if body.is_comment_enabled is not None and body.is_comment_enabled != media.is_comment_enabled:
        media_service = container.media_service()
        result = await media_service.set_comment_status(media_id, bool(body.is_comment_enabled), session)
        if not result.get("success"):
            logger.error(
                "Failed to update Instagram comment status | media_id=%s | response=%s",
                media_id,
                result,
            )
            raise JsonApiError(502, 5002, "Failed to update Instagram comment status")
        updated_comment_status = True

    if body.context is not None:
        media.media_context = str(body.context)

    if body.is_processing_enabled is not None:
        media.is_processing_enabled = bool(body.is_processing_enabled)

    await session.commit()
    if updated_comment_status:
        await session.refresh(media)

    logger.info(
        "Media updated | media_id=%s | updated_comment_status=%s",
        media_id,
        updated_comment_status,
    )

    stats_map = await _get_media_stats_map(session, [media.id])
    return MediaResponse(meta=SimpleMeta(), payload=serialize_media(media, stats=stats_map.get(media.id)))


@router.get("/media/{id}/image")
async def proxy_media_image(
    _: None = Depends(require_service_token),
    media_id: str = Path(..., alias="id"),
    child_index: Optional[int] = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    container = get_container()
    use_case = container.proxy_media_image_use_case(session=session)

    try:
        result = await use_case.execute(media_id=media_id, child_index=child_index)
    except MediaImageProxyError as exc:
        logger.error(
            "Proxy media image failed | media_id=%s | child_index=%s | code=%s | message=%s",
            media_id,
            child_index,
            exc.code,
            exc.message,
        )
        raise JsonApiError(exc.status_code, exc.code, exc.message)

    fetch_result = result.fetch_result

    async def _stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in fetch_result.iter_bytes():
                yield chunk
        finally:
            await fetch_result.close()

    response = StreamingResponse(
        _stream(),
        media_type=fetch_result.content_type or "application/octet-stream",
    )
    if fetch_result.cache_control:
        response.headers["Cache-Control"] = fetch_result.cache_control

    logger.debug(
        "Proxy media image succeeded | media_id=%s | child_index=%s | url=%s",
        media_id,
        child_index,
        result.media_url,
    )
    return response


@router.get("/media/{id}/comments")
async def list_media_comments(
    _: None = Depends(require_service_token),
    media_id: str = Path(..., alias="id"),
    page: int = Query(1, ge=1),
    per_page: int = Query(COMMENTS_DEFAULT_PER_PAGE, ge=1),
    include_deleted: bool = Query(True, description="Include comments marked as deleted"),
    status_multi: Optional[List[int]] = Query(default=None, alias="status[]"),
    status_csv: Optional[str] = Query(default=None, alias="status"),
    classification_multi: Optional[List[int]] = Query(default=None, alias="type[]"),
    classification_csv: Optional[str] = Query(default=None, alias="type"),
    classification_multi_alt: Optional[List[int]] = Query(default=None, alias="classification_type[]"),
    classification_csv_alt: Optional[str] = Query(default=None, alias="classification_type"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    await _get_media_or_404(session, media_id)
    per_page = _clamp_per_page(per_page, COMMENTS_DEFAULT_PER_PAGE, COMMENTS_MAX_PER_PAGE)
    offset = (page - 1) * per_page
    statuses, classification_types = _parse_comment_filters(
        status_multi=status_multi,
        status_csv=status_csv,
        classification_multi=classification_multi,
        classification_csv=classification_csv,
        classification_multi_alt=classification_multi_alt,
        classification_csv_alt=classification_csv_alt,
    )

    repo = CommentRepository(session)
    total = await repo.count_for_media(
        media_id,
        statuses=statuses,
        classification_types=classification_types,
        include_deleted=include_deleted,
    )
    items = await repo.list_for_media(
        media_id,
        offset=offset,
        limit=per_page,
        statuses=statuses,
        classification_types=classification_types,
        include_deleted=include_deleted,
    )
    payload = [serialize_comment(comment) for comment in items]
    response = CommentListResponse(
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
        payload=payload,
    )
    return response


@router.get("/comments")
async def list_recent_comments(
    _: None = Depends(require_service_token),
    page: int = Query(1, ge=1),
    per_page: int = Query(COMMENTS_DEFAULT_PER_PAGE, ge=1),
    include_deleted: bool = Query(True, description="Include comments marked as deleted"),
    status_multi: Optional[List[int]] = Query(default=None, alias="status[]"),
    status_csv: Optional[str] = Query(default=None, alias="status"),
    classification_multi: Optional[List[int]] = Query(default=None, alias="type[]"),
    classification_csv: Optional[str] = Query(default=None, alias="type"),
    classification_multi_alt: Optional[List[int]] = Query(default=None, alias="classification_type[]"),
    classification_csv_alt: Optional[str] = Query(default=None, alias="classification_type"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    per_page = _clamp_per_page(per_page, COMMENTS_DEFAULT_PER_PAGE, COMMENTS_MAX_PER_PAGE)
    offset = (page - 1) * per_page
    statuses, classification_types = _parse_comment_filters(
        status_multi=status_multi,
        status_csv=status_csv,
        classification_multi=classification_multi,
        classification_csv=classification_csv,
        classification_multi_alt=classification_multi_alt,
        classification_csv_alt=classification_csv_alt,
    )

    repo = CommentRepository(session)
    total = await repo.count_all(
        statuses=statuses,
        classification_types=classification_types,
        include_deleted=include_deleted,
    )
    items = await repo.list_recent(
        offset=offset,
        limit=per_page,
        statuses=statuses,
        classification_types=classification_types,
        include_deleted=include_deleted,
    )
    payload = [serialize_comment(comment) for comment in items]
    stats = await _get_comment_quick_stats(session)
    response = CommentListResponse(
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
        payload=payload,
        stats=stats,
    )
    return response


@router.delete("/comments/{id}")
async def delete_comment(
    _: None = Depends(require_service_token),
    comment_id: str = Path(..., alias="id"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    container = get_container()
    use_case: DeleteCommentUseCase = container.delete_comment_use_case(session=session)
    result = await use_case.execute(comment_id, initiator="manual")
    status = result.get("status")
    if status == "error":
        reason = result.get("reason")
        if isinstance(reason, str) and "not found" in reason.lower():
            raise JsonApiError(404, 4041, "Comment not found")
        raise JsonApiError(502, 5004, "Failed to delete comment")
    return EmptyResponse(meta=SimpleMeta())


@router.patch("/comments/{id}")
async def patch_comment_visibility(
    _: None = Depends(require_service_token),
    comment_id: str = Path(..., alias="id"),
    is_hidden: bool = Query(..., description="Hide or unhide the comment"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    container = get_container()
    use_case: HideCommentUseCase = container.hide_comment_use_case(session=session)
    result = await use_case.execute(comment_id, hide=is_hidden, initiator="manual")
    status = result.get("status")
    if status == "error":
        raise JsonApiError(502, 5003, "Failed to update comment visibility")
    if status == "retry":
        raise JsonApiError(502, 5003, "Temporary error hiding comment")

    comment = await _get_comment_or_404(session, comment_id)
    return CommentResponse(meta=SimpleMeta(), payload=serialize_comment(comment))


@router.patch("/comments/{id}/classification")
async def patch_comment_classification(
    _: None = Depends(require_service_token),
    comment_id: str = Path(..., alias="id"),
    body: ClassificationUpdateRequest = Body(...),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    normalized_label = normalize_classification_label(str(body.type))
    if not normalized_label:
        raise JsonApiError(400, 4009, "Unknown classification type")
    reasoning = str(body.reasoning).strip()

    repo = ClassificationRepository(session)
    classification: Optional[CommentClassification] = await repo.get_by_comment_id(comment_id)
    if not classification:
        classification = CommentClassification(comment_id=comment_id)
        session.add(classification)

    completed_at = now_db_utc()
    if classification.id is None:
        classification.type = normalized_label
        classification.reasoning = reasoning
        classification.confidence = None
        classification.processing_status = ProcessingStatus.COMPLETED
        classification.processing_completed_at = completed_at
        classification.last_error = None
    else:
        await session.execute(
            update(CommentClassification)
            .where(CommentClassification.id == classification.id)
            .values(
                type=normalized_label,
                reasoning=reasoning,
                confidence=None,
                processing_status=ProcessingStatus.COMPLETED,
                processing_completed_at=completed_at,
                last_error=None,
            )
        )
    await session.commit()

    comment = await _get_comment_or_404(session, comment_id)
    return CommentResponse(meta=SimpleMeta(), payload=serialize_comment(comment))


@router.get("/comments/{id}/answers")
async def list_answers_for_comment(
    _: None = Depends(require_service_token),
    comment_id: str = Path(..., alias="id"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    comment = await _get_comment_or_404(session, comment_id)
    answers = []
    if comment.question_answer:
        answers.append(serialize_answer(comment.question_answer))
    return AnswerListResponse(meta=SimpleMeta(), payload=answers)


@router.put("/comments/{comment_id}/answers")
async def create_answer(
    _: None = Depends(require_service_token),
    comment_id: str = Path(...),
    body: AnswerCreateRequest = Body(...),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    container = get_container()
    use_case = container.create_manual_answer_use_case(session=session)
    try:
        answer = await use_case.execute(comment_id=comment_id, answer_text=str(body.answer))
    except ManualAnswerCreateError as exc:
        if exc.status_code == 404:
            raise JsonApiError(404, 4041, "Comment not found")
        raise JsonApiError(502, 5007, str(exc))

    return AnswerResponse(meta=SimpleMeta(), payload=serialize_answer(answer))


@router.patch("/answers/{id}")
async def patch_answer(
    _: None = Depends(require_service_token),
    answer_id: int = Path(..., alias="id"),
    body: AnswerUpdateRequest = Body(...),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    container = get_container()
    use_case = container.replace_answer_use_case(session=session)
    try:
        new_answer = await use_case.execute(
            answer_id=answer_id,
            new_answer_text=str(body.answer),
            quality_score=body.quality_score,
        )
    except ReplaceAnswerError as exc:
        message = str(exc)
        if message == "Answer not found":
            raise JsonApiError(404, 4042, "Answer not found")
        raise JsonApiError(502, 5005, message)
    except Exception:
        logger.exception("Unexpected error while replacing answer | answer_id=%s", answer_id)
        raise JsonApiError(502, 5005, "Failed to replace answer")

    return AnswerResponse(meta=SimpleMeta(), payload=serialize_answer(new_answer))


@router.delete("/answers/{id}")
async def delete_answer(
    _: None = Depends(require_service_token),
    answer_id: int = Path(..., alias="id"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    answer = await _get_answer_for_update_or_404(session, answer_id)
    if not answer.reply_id or answer.reply_status == "deleted":
        raise JsonApiError(400, 4012, "Answer does not have an Instagram reply")

    instagram_service = get_container().instagram_service()
    result = await instagram_service.delete_comment_reply(answer.reply_id)
    if not result.get("success"):
        raise JsonApiError(502, 5004, "Failed to delete reply on Instagram")

    answer.reply_sent = False
    answer.reply_status = "deleted"
    answer.reply_error = None
    answer.is_deleted = True
    await session.commit()
    return EmptyResponse(meta=SimpleMeta())


@router.get("/meta/classification-types")
async def get_classification_types(
    _: None = Depends(require_service_token),
):
    items = [ClassificationTypeDTO(code=code, label=label) for code, label in list_classification_types()]
    return ClassificationTypesResponse(meta=SimpleMeta(), payload=items)
