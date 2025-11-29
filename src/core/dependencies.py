"""
FastAPI dependencies for dependency injection.

Provides easy integration between FastAPI's dependency system
and the application's DI container.
"""

from typing import Callable
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .container import get_container, Container
from .models import db_helper
from .interfaces.services import (
    ITaskQueue,
    IS3Service,
    IDocumentProcessingService,
    IDocumentContextService,
)

# Import use cases
from .use_cases.classify_comment import ClassifyCommentUseCase
from .use_cases.generate_answer import GenerateAnswerUseCase
from .use_cases.send_reply import SendReplyUseCase
from .use_cases.hide_comment import HideCommentUseCase
from .use_cases.delete_comment import DeleteCommentUseCase
from .use_cases.process_webhook_comment import ProcessWebhookCommentUseCase
from .use_cases.send_telegram_notification import SendTelegramNotificationUseCase
from .use_cases.process_media import ProcessMediaUseCase, AnalyzeMediaUseCase
from .use_cases.process_document import ProcessDocumentUseCase
from .use_cases.test_comment_processing import TestCommentProcessingUseCase
from .use_cases.generate_stats_report import GenerateStatsReportUseCase, StatsPeriod
from .use_cases.generate_moderation_stats import GenerateModerationStatsUseCase

# Import repositories
from .repositories.comment import CommentRepository
from .repositories.answer import AnswerRepository


# ============================================================================
# Repository Dependencies
# ============================================================================


def get_comment_repository(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
) -> CommentRepository:
    """Provide CommentRepository with session injected."""
    return CommentRepository(session)


def get_answer_repository(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
) -> AnswerRepository:
    """Provide AnswerRepository with session injected."""
    return AnswerRepository(session)


# ============================================================================
# Use Case Dependencies
# ============================================================================


def get_classify_comment_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> ClassifyCommentUseCase:
    """
    Provide ClassifyCommentUseCase with all dependencies injected.

    Usage in endpoint:
        async def my_endpoint(
            use_case: ClassifyCommentUseCase = Depends(get_classify_comment_use_case)
        ):
            result = await use_case.execute(comment_id)
    """
    return container.classify_comment_use_case(session=session)


def get_generate_answer_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> GenerateAnswerUseCase:
    """Provide GenerateAnswerUseCase with dependencies."""
    return container.generate_answer_use_case(session=session)


def get_send_reply_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> SendReplyUseCase:
    """Provide SendReplyUseCase with dependencies."""
    return container.send_reply_use_case(session=session)


def get_hide_comment_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> HideCommentUseCase:
    """Provide HideCommentUseCase with dependencies."""
    return container.hide_comment_use_case(session=session)


def get_delete_comment_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> DeleteCommentUseCase:
    """Provide DeleteCommentUseCase with dependencies."""
    return container.delete_comment_use_case(session=session)


def get_process_webhook_comment_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> ProcessWebhookCommentUseCase:
    """Provide ProcessWebhookCommentUseCase with dependencies."""
    return container.process_webhook_comment_use_case(session=session)


def get_send_telegram_notification_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> SendTelegramNotificationUseCase:
    """Provide SendTelegramNotificationUseCase with dependencies."""
    return container.send_telegram_notification_use_case(session=session)


def get_process_media_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> ProcessMediaUseCase:
    """Provide ProcessMediaUseCase with dependencies."""
    return container.process_media_use_case(session=session)


def get_analyze_media_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> AnalyzeMediaUseCase:
    """Provide AnalyzeMediaUseCase with dependencies."""
    return container.analyze_media_use_case(session=session)


def get_process_document_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> ProcessDocumentUseCase:
    """Provide ProcessDocumentUseCase with dependencies."""
    return container.process_document_use_case(session=session)


def get_test_comment_processing_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> TestCommentProcessingUseCase:
    """Provide TestCommentProcessingUseCase with dependencies."""
    return container.test_comment_processing_use_case(session=session)


def get_generate_stats_report_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> GenerateStatsReportUseCase:
    """Provide GenerateStatsReportUseCase."""
    return container.generate_stats_report_use_case(session=session)


def get_generate_moderation_stats_use_case(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> GenerateModerationStatsUseCase:
    """Provide GenerateModerationStatsUseCase."""
    return container.generate_moderation_stats_use_case(session=session)


# Generic factory for creating dependency providers
def create_use_case_dependency(use_case_factory: Callable) -> Callable:
    """
    Generic factory for creating FastAPI dependency functions.

    Args:
        use_case_factory: Container factory method for the use case

    Returns:
        FastAPI dependency function

    Example:
        get_my_use_case = create_use_case_dependency(
            lambda container, session: container.my_use_case(session=session)
        )
    """

    def dependency(
        session: AsyncSession = Depends(db_helper.scoped_session_dependency),
        container: Container = Depends(get_container),
    ):
        return use_case_factory(container, session)

    return dependency


# ============================================================================
# Infrastructure Dependencies
# ============================================================================


def get_task_queue(container: Container = Depends(get_container)) -> ITaskQueue:
    """Provide task queue interface from DI container."""
    return container.task_queue()


def get_s3_service(container: Container = Depends(get_container)) -> IS3Service:
    """Provide S3 service abstraction."""
    return container.s3_service()


def get_document_processing_service(
    container: Container = Depends(get_container),
) -> IDocumentProcessingService:
    """Provide document processing service abstraction."""
    return container.document_processing_service()


def get_document_context_service(
    container: Container = Depends(get_container),
) -> IDocumentContextService:
    """Provide document context retrieval service."""
    return container.document_context_service()
