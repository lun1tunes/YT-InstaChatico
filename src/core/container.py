"""
Dependency Injection Container.

Centralizes all dependency configuration following the Dependency Inversion Principle.
This makes the application more testable and maintainable.
"""

from dependency_injector import containers, providers
from redis import asyncio as redis_async

from .config import settings

# Services
from .services.classification_service import CommentClassificationService
from .services.answer_service import QuestionAnswerService
from .services.instagram_service import InstagramGraphAPIService
from .services.media_service import MediaService
from .services.media_analysis_service import MediaAnalysisService
from .services.embedding_service import EmbeddingService
from .services.telegram_alert_service import TelegramAlertService
from .services.s3_service import S3Service
from .services.youtube_service import YouTubeService
from .services.youtube_media_service import YouTubeMediaService
from .services.document_processing_service import DocumentProcessingService
from .services.document_context_service import DocumentContextService
from .services.agent_session_service import AgentSessionService
from .services.agent_executor import AgentExecutor
from .services.rate_limiter import RedisRateLimiter
from .services.media_proxy_service import MediaProxyService
from .services.tools_token_usage_inspector import ToolsTokenUsageInspector

# Infrastructure
from .infrastructure.task_queue import CeleryTaskQueue
from .celery_app import celery_app
from .models.db_helper import db_helper

# Use cases
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
from .use_cases.proxy_media_image import ProxyMediaImageUseCase
from .use_cases.replace_answer import ReplaceAnswerUseCase
from .use_cases.create_manual_answer import CreateManualAnswerUseCase
from .use_cases.generate_stats_report import GenerateStatsReportUseCase
from .use_cases.generate_moderation_stats import GenerateModerationStatsUseCase
from .use_cases.record_follower_snapshot import RecordFollowerSnapshotUseCase
from .use_cases.poll_youtube_comments import PollYouTubeCommentsUseCase
from .use_cases.send_youtube_reply import SendYouTubeReplyUseCase
from .use_cases.delete_youtube_comment import DeleteYouTubeCommentUseCase

# Repositories
from .repositories.comment import CommentRepository
from .repositories.classification import ClassificationRepository
from .repositories.answer import AnswerRepository
from .repositories.media import MediaRepository
from .repositories.document import DocumentRepository
from .repositories.instrument_token_usage import InstrumentTokenUsageRepository
from .repositories.stats_report import StatsReportRepository
from .repositories.moderation_stats import ModerationStatsRepository
from .repositories.moderation_stats_report import ModerationStatsReportRepository
from .repositories.followers_dynamic import FollowersDynamicRepository
from .repositories.oauth_token import OAuthTokenRepository
from .services.oauth_token_service import OAuthTokenService


class Container(containers.DeclarativeContainer):
    """
    Application DI container.

    Provides centralized configuration for all dependencies.
    Services are created as singletons or factories as appropriate.
    """

    # Configuration
    config = providers.Configuration()

    # Infrastructure - Singleton
    task_queue = providers.Singleton(
        CeleryTaskQueue,
        celery_app=celery_app,
    )

    instagram_rate_limit_redis = providers.Singleton(
        redis_async.Redis.from_url,
        settings.instagram.rate_limit_redis_url,
    )

    instagram_rate_limiter = providers.Singleton(
        RedisRateLimiter,
        redis_client=instagram_rate_limit_redis,
        key="instagram:replies",
        limit=settings.instagram.replies_rate_limit_per_hour,
        period=settings.instagram.replies_rate_period_seconds,
        owns_connection=False,
    )

    youtube_rate_limit_redis = providers.Singleton(
        redis_async.Redis.from_url,
        settings.youtube.rate_limit_redis_url,
    )

    youtube_rate_limiter = providers.Singleton(
        RedisRateLimiter,
        redis_client=youtube_rate_limit_redis,
        key="youtube:comments",
        limit=500,  # placeholder; tune to match quotas
        period=60,
        owns_connection=False,
    )

    # Database infrastructure
    database_helper = providers.Object(db_helper)
    db_engine = providers.Callable(lambda helper: helper.engine, database_helper)
    db_session_factory = providers.Callable(lambda helper: helper.session_factory, database_helper)
    db_scoped_session = providers.Callable(lambda helper: helper.session_factory, database_helper)

    # Repository factories
    comment_repository_factory = providers.Factory(CommentRepository)
    classification_repository_factory = providers.Factory(ClassificationRepository)
    answer_repository_factory = providers.Factory(AnswerRepository)
    media_repository_factory = providers.Factory(MediaRepository)
    document_repository_factory = providers.Factory(DocumentRepository)
    instrument_token_usage_repository_factory = providers.Factory(InstrumentTokenUsageRepository)
    stats_report_repository_factory = providers.Factory(StatsReportRepository)
    moderation_stats_repository_factory = providers.Factory(ModerationStatsRepository)
    moderation_stats_report_repository_factory = providers.Factory(ModerationStatsReportRepository)
    followers_dynamic_repository_factory = providers.Factory(FollowersDynamicRepository)
    oauth_token_repository_factory = providers.Factory(OAuthTokenRepository)

    agent_session_service = providers.Singleton(
        AgentSessionService,
    )

    agent_executor = providers.Singleton(
        AgentExecutor,
    )

    # Services - Factory (new instance each time, allows different configs)
    classification_service = providers.Factory(
        CommentClassificationService,
        agent_executor=agent_executor,
        session_service=agent_session_service,
    )

    answer_service = providers.Factory(
        QuestionAnswerService,
        agent_executor=agent_executor,
        session_service=agent_session_service,
    )

    instagram_service = providers.Singleton(
        InstagramGraphAPIService,
        rate_limiter=instagram_rate_limiter,
    )

    media_service = providers.Factory(
        MediaService,
        instagram_service=instagram_service,
        task_queue=task_queue,
    )

    embedding_service = providers.Factory(
        EmbeddingService,
    )

    telegram_service = providers.Factory(
        TelegramAlertService,
    )

    log_alert_service = providers.Singleton(
        TelegramAlertService,
        alert_type="app_logs",
    )

    media_analysis_service = providers.Factory(
        MediaAnalysisService,
    )

    youtube_service = providers.Singleton(
        YouTubeService,
        token_service_factory=oauth_token_service.provider,
        session_factory=db_session_factory.provider,
    )
    youtube_media_service = providers.Factory(
        YouTubeMediaService,
        youtube_service=youtube_service,
    )

    media_proxy_service = providers.Singleton(
        MediaProxyService,
        timeout_seconds=settings.media_proxy.request_timeout_seconds,
    )

    s3_service = providers.Singleton(
        S3Service,
    )

    document_processing_service = providers.Singleton(
        DocumentProcessingService,
    )

    document_context_service = providers.Singleton(
        DocumentContextService,
    )

    oauth_token_service = providers.Factory(
        OAuthTokenService,
        repository_factory=oauth_token_repository_factory.provider,
        encryption_key=settings.oauth_encryption_key,
    )

    proxy_media_image_use_case = providers.Factory(
        ProxyMediaImageUseCase,
        media_repository_factory=media_repository_factory.provider,
        proxy_service=media_proxy_service,
        media_service=media_service,
        allowed_host_suffixes=settings.media_proxy.allowed_host_suffixes,
    )

    tools_token_usage_inspector = providers.Factory(
        ToolsTokenUsageInspector,
        repository_factory=instrument_token_usage_repository_factory.provider,
        session_factory=db_session_factory.provider,
    )

    # Use Cases - Factory (new instance per request)
    # Note: session is provided at call time via Depends()

    classify_comment_use_case = providers.Factory(
        ClassifyCommentUseCase,
        # session is injected at runtime
        comment_repository_factory=comment_repository_factory.provider,
        classification_repository_factory=classification_repository_factory.provider,
        classification_service=classification_service,
        media_service=youtube_media_service,
    )

    generate_answer_use_case = providers.Factory(
        GenerateAnswerUseCase,
        # session is injected at runtime
        comment_repository_factory=comment_repository_factory.provider,
        answer_repository_factory=answer_repository_factory.provider,
        qa_service=answer_service,
    )

    send_reply_use_case = providers.Factory(
        SendReplyUseCase,
        # session is injected at runtime
        comment_repository_factory=comment_repository_factory.provider,
        answer_repository_factory=answer_repository_factory.provider,
        instagram_service=instagram_service,
    )

    hide_comment_use_case = providers.Factory(
        HideCommentUseCase,
        # session is injected at runtime
        comment_repository_factory=comment_repository_factory.provider,
        instagram_service=instagram_service,
    )

    delete_comment_use_case = providers.Factory(
        DeleteCommentUseCase,
        # session is injected at runtime
        comment_repository_factory=comment_repository_factory.provider,
        instagram_service=instagram_service,
    )

    replace_answer_use_case = providers.Factory(
        ReplaceAnswerUseCase,
        # session is injected at runtime
        answer_repository_factory=answer_repository_factory.provider,
        instagram_service=instagram_service,
    )

    create_manual_answer_use_case = providers.Factory(
        CreateManualAnswerUseCase,
        # session is injected at runtime
        comment_repository_factory=comment_repository_factory.provider,
        answer_repository_factory=answer_repository_factory.provider,
        instagram_service=instagram_service,
        replace_answer_use_case_factory=replace_answer_use_case.provider,
        session_service=agent_session_service,
    )

    process_webhook_comment_use_case = providers.Factory(
        ProcessWebhookCommentUseCase,
        # session is injected at runtime
        comment_repository_factory=comment_repository_factory.provider,
        media_repository_factory=media_repository_factory.provider,
        media_service=media_service,
        task_queue=task_queue,
    )

    send_telegram_notification_use_case = providers.Factory(
        SendTelegramNotificationUseCase,
        # session is injected at runtime
        comment_repository_factory=comment_repository_factory.provider,
        telegram_service=telegram_service,
    )

    process_media_use_case = providers.Factory(
        ProcessMediaUseCase,
        # session is injected at runtime
        media_repository_factory=media_repository_factory.provider,
        media_service=media_service,
        analysis_service=media_analysis_service,
    )

    analyze_media_use_case = providers.Factory(
        AnalyzeMediaUseCase,
        # session is injected at runtime
        media_repository_factory=media_repository_factory.provider,
        analysis_service=media_analysis_service,
    )

    poll_youtube_comments_use_case = providers.Factory(
        PollYouTubeCommentsUseCase,
        # session is injected at runtime
        youtube_service=youtube_service,
        youtube_media_service=youtube_media_service,
        task_queue=task_queue,
        comment_repository_factory=comment_repository_factory.provider,
        media_repository_factory=media_repository_factory.provider,
        classification_repository_factory=classification_repository_factory.provider,
    )

    send_youtube_reply_use_case = providers.Factory(
        SendYouTubeReplyUseCase,
        youtube_service=youtube_service,
        comment_repository_factory=comment_repository_factory.provider,
        answer_repository_factory=answer_repository_factory.provider,
    )

    delete_youtube_comment_use_case = providers.Factory(
        DeleteYouTubeCommentUseCase,
        youtube_service=youtube_service,
        comment_repository_factory=comment_repository_factory.provider,
    )

    process_document_use_case = providers.Factory(
        ProcessDocumentUseCase,
        # session is injected at runtime
        document_repository_factory=document_repository_factory.provider,
        s3_service=s3_service,
        doc_processing_service=document_processing_service,
    )

    test_comment_processing_use_case = providers.Factory(
        TestCommentProcessingUseCase,
        # session is injected at runtime
        comment_repository_factory=comment_repository_factory.provider,
        media_repository_factory=media_repository_factory.provider,
        # Optional use cases will use container if not provided
    )

    generate_stats_report_use_case = providers.Factory(
        GenerateStatsReportUseCase,
        stats_report_repository_factory=stats_report_repository_factory.provider,
        instagram_service=instagram_service,
    )

    generate_moderation_stats_use_case = providers.Factory(
        GenerateModerationStatsUseCase,
        moderation_stats_repository_factory=moderation_stats_repository_factory.provider,
        moderation_stats_report_repository_factory=moderation_stats_report_repository_factory.provider,
    )

    record_follower_snapshot_use_case = providers.Factory(
        RecordFollowerSnapshotUseCase,
        followers_dynamic_repository_factory=followers_dynamic_repository_factory.provider,
        instagram_service=instagram_service,
    )


# Global container instance
container = Container()


def get_container() -> Container:
    """
    Get the global container instance.

    Used as a FastAPI dependency:
        container: Container = Depends(get_container)
    """
    return container


def reset_container():
    """
    Reset container for testing.

    Clears all singletons and allows fresh initialization.
    """
    container.reset_singletons()
