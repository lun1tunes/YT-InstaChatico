"""Instagram webhook endpoints for comment processing."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging_config import trace_id_ctx
from core.models import db_helper
from core.schemas.webhook import WebhookProcessingResponse, TestCommentResponse
from core.use_cases.process_webhook_comment import ProcessWebhookCommentUseCase
from core.use_cases.test_comment_processing import TestCommentProcessingUseCase
from core.dependencies import (
    get_process_webhook_comment_use_case,
    get_test_comment_processing_use_case,
    get_answer_repository,
    get_task_queue,
)
from core.repositories.answer import AnswerRepository
from core.interfaces.services import ITaskQueue

from .helpers import should_skip_comment, extract_comment_data
from .schemas import TestCommentPayload, WebhookPayload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Webhooks"])


@router.get("/")
async def webhook_verification(request: Request):
    """Handle Instagram webhook verification challenge."""
    hub_mode = request.query_params.get("hub.mode")
    hub_challenge = request.query_params.get("hub.challenge")
    hub_verify_token = request.query_params.get("hub.verify_token")

    if not all([hub_mode, hub_challenge, hub_verify_token]):
        raise HTTPException(status_code=422, detail="Missing required parameters")

    if settings.app_webhook_verify_token and hub_verify_token != settings.app_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token")

    logger.info("Webhook verification successful")
    return PlainTextResponse(hub_challenge)


@router.post("")
@router.post("/")
async def process_webhook(
    webhook_data: WebhookPayload,
    request: Request,
    process_use_case: ProcessWebhookCommentUseCase = Depends(get_process_webhook_comment_use_case),
    answer_repo: AnswerRepository = Depends(get_answer_repository),
    task_queue: ITaskQueue = Depends(get_task_queue),
):
    """Process Instagram webhook for new comments."""
    # Bind trace ID early if provided
    if incoming_trace := request.headers.get("X-Trace-Id"):
        trace_id_ctx.set(incoming_trace)

    logger.info("Processing webhook request")

    processed_count = 0
    skipped_count = 0

    try:
        # Extract all comments from webhook
        comments = webhook_data.get_all_comments()
        logger.info(f"Webhook received {len(comments)} comment(s)")

        for entry, comment in comments:
            comment_id = comment.id

            try:
                # Check if comment should be skipped (bot loops, etc.)
                should_skip, skip_reason = await should_skip_comment(comment, answer_repo)
                if should_skip:
                    logger.info(f"Skipping comment {comment_id}: {skip_reason}")
                    skipped_count += 1
                    continue

                # Process comment using Use Case
                comment_data = extract_comment_data(comment, entry.time)

                result = await process_use_case.execute(
                    comment_id=comment_id,
                    media_id=comment_data["media_id"],
                    user_id=comment_data["user_id"],
                    username=comment_data["username"],
                    text=comment_data["text"],
                    entry_timestamp=entry.time,
                    parent_id=comment_data.get("parent_id"),
                    raw_data=comment_data.get("raw_data"),
                    entry_owner_id=entry.id,
                )

                status = result.get("status", "error")
                if status == "forbidden":
                    logger.warning(
                        "Rejecting webhook due to media owner validation | comment_id=%s | reason=%s",
                        comment_id,
                        result.get("reason"),
                    )
                    raise HTTPException(status_code=403, detail=result.get("reason", "Invalid webhook account"))

                # Queue classification if needed
                if result.get("should_classify"):
                    task_queue.enqueue(
                        "core.tasks.classification_tasks.classify_comment_task",
                        comment_id,
                    )
                    logger.info(f"Comment {comment_id} queued for classification")

                if status == "created":
                    processed_count += 1
                else:
                    skipped_count += 1

            except HTTPException:
                raise
            except Exception:
                logger.exception(f"Error processing comment {comment_id}")
                skipped_count += 1

        logger.info(f"Webhook complete: {processed_count} new, {skipped_count} skipped")
        logger.debug(f"Payload entry:{webhook_data.entry}")
        return WebhookProcessingResponse(
            status="success",
            message=f"Processed {processed_count} new comments, skipped {skipped_count}",
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error processing webhook")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test", tags=["Testing"])
async def test_comment_processing(
    test_data: TestCommentPayload,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    test_use_case: TestCommentProcessingUseCase = Depends(get_test_comment_processing_use_case),
):
    """
    Test endpoint for Instagram comment processing (DEVELOPMENT_MODE only).

    This endpoint processes comments through the full pipeline (classification → answer generation)
    but returns the answer in the response instead of posting to Instagram.
    All database records are created as in production mode.

    Only accessible when dev mode is enabled.
    """
    # Check if development mode is enabled
    development_mode = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"
    if not development_mode:
        raise HTTPException(status_code=403, detail="Test endpoint only accessible in dev mode")

    logger.info(f"Processing test comment: {test_data.comment_id}")

    try:
        # Process test comment using Use Case
        result = await test_use_case.execute(
            comment_id=test_data.comment_id,
            media_id=test_data.media_id,
            user_id=test_data.user_id,
            username=test_data.username,
            text=test_data.text,
            parent_id=test_data.parent_id,
            media_caption=test_data.media_caption,
            media_url=test_data.media_url,
        )

        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result.get("reason"))

        logger.info(
            f"Test comment processing complete. Classification: {result.get('classification')}, "
            f"Answer: {bool(result.get('answer'))}"
        )

        return TestCommentResponse(
            status="success",
            message=f"Test comment processed: {result.get('classification')}",
            comment_id=test_data.comment_id,
            classification=result.get("classification"),
            answer=result.get("answer"),
            processing_details=result.get("processing_details"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing test comment {test_data.comment_id}")
        raise HTTPException(status_code=500, detail=f"Error processing test comment: {str(e)}")
