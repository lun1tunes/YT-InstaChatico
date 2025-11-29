from celery import Celery
from celery.schedules import crontab
from datetime import timedelta
from .config import settings
import os
from celery.signals import before_task_publish, task_prerun
from core.logging_config import trace_id_ctx

celery_app = Celery(
    "youtube_comment_manager",
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
    include=[
        "core.tasks.classification_tasks",
        "core.tasks.answer_tasks",
        "core.tasks.instagram_reply_tasks",
        "core.tasks.telegram_tasks",
        "core.tasks.health_tasks",
        "core.tasks.media_tasks",
        "core.tasks.document_tasks",
        "core.tasks.instagram_token_tasks",
        "core.tasks.stats_tasks",
        "core.tasks.youtube_tasks",
    ],
)

# Configure broker connection resilience
celery_app.conf.broker_connection_retry_on_startup = True
celery_app.conf.broker_connection_retry = True
celery_app.conf.broker_connection_max_retries = 30

# Redis-specific configuration for handling failover and read-only replicas
celery_app.conf.broker_transport_options = {
    'visibility_timeout': 3600,  # 1 hour
    'fanout_prefix': True,
    'fanout_patterns': True,
    'retry_on_timeout': True,
    'max_connections': 10,
}

# Result backend options for Redis resilience
celery_app.conf.result_backend_transport_options = {
    'retry_on_timeout': True,
    'max_connections': 10,
}

# Настройки Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    # Keep Celery from reconfiguring root logger; we configure in celery_worker.py
    worker_hijack_root_logger=False,
    # Unify Celery's own log formats with our console formatter
    worker_log_format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    worker_task_log_format="%(asctime)s | %(levelname)s | %(task_name)s[%(task_id)s] | %(message)s",
    # Redirect stdout/stderr to suppress banner noise at WARNING level
    worker_redirect_stdouts=True,
    worker_redirect_stdouts_level="WARNING",
    # Suppress verbose Celery startup output
    worker_log_color=False,
    worker_disable_rate_limits=True,
    task_routes={
        "core.tasks.classification_tasks.classify_comment_task": {"queue": "llm_queue"},
        "core.tasks.answer_tasks.generate_answer_task": {"queue": "llm_queue"},
        "core.tasks.media_tasks.analyze_media_image_task": {"queue": "llm_queue"},
        "core.tasks.document_tasks.process_document_task": {"queue": "llm_queue"},
        "core.tasks.instagram_reply_tasks.send_instagram_reply_task": {"queue": "instagram_queue"},
        "core.tasks.instagram_reply_tasks.hide_instagram_comment_task": {"queue": "instagram_queue"},
        "core.tasks.telegram_tasks.send_telegram_notification_task": {"queue": "instagram_queue"},
        # YouTube moderation/replies
        "core.tasks.youtube_tasks.poll_youtube_comments_task": {"queue": "youtube_queue"},
        "core.tasks.youtube_tasks.send_youtube_reply_task": {"queue": "youtube_queue"},
        "core.tasks.youtube_tasks.delete_youtube_comment_task": {"queue": "youtube_queue"},
        # Periodic/scheduled jobs – route them explicitly so Celery Beat doesn't fall back to the default queue
        "core.tasks.classification_tasks.retry_failed_classifications": {"queue": "llm_queue"},
        "core.tasks.health_tasks.check_system_health_task": {"queue": "instagram_queue"},
        "core.tasks.instagram_token_tasks.check_instagram_token_expiration_task": {"queue": "instagram_queue"},
        "core.tasks.stats_tasks.record_follower_snapshot_task": {"queue": "instagram_queue"},
    },
    task_soft_time_limit=300,
    task_time_limit=600,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=50,
    # Suppress deprecation warning about task cancellation on connection loss
    # This will be the default behavior in Celery 6.0
    worker_cancel_long_running_tasks_on_connection_loss=True,
)

# Периодические задачи - ONLY tasks that actually exist!
celery_app.conf.beat_schedule = {
    "retry-failed-classifications": {
        "task": "core.tasks.classification_tasks.retry_failed_classifications",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
    "check-system-health": {
        "task": "core.tasks.health_tasks.check_system_health_task",
        "schedule": crontab(minute=0, hour="*"),
    },
    "record-instagram-followers": {
        "task": "core.tasks.stats_tasks.record_follower_snapshot_task",
        # enable_utc=True ensures this executes at 00:00 UTC
        "schedule": crontab(minute=0, hour=0),
    },
    "poll-youtube-comments": {
        "task": "core.tasks.youtube_tasks.poll_youtube_comments_task",
        "schedule": timedelta(seconds=settings.youtube.poll_interval_seconds),
        "options": {"queue": "youtube_queue"},
    },
}


@celery_app.on_after_configure.connect
def run_initial_health_check(sender, **kwargs):
    """Ensure a health snapshot runs once on startup for immediate visibility."""
    try:
        sender.send_task(
            "core.tasks.health_tasks.check_system_health_task",
            countdown=5,
        )
    except Exception:
        # Avoid crashing startup if broker temporarily unavailable
        pass


# Propagate trace_id via Celery headers
@before_task_publish.connect
def add_trace_id_on_publish(headers=None, body=None, **kwargs):
    trace_id = trace_id_ctx.get()
    if trace_id:
        headers = headers or {}
        headers.setdefault("trace_id", trace_id)


@task_prerun.connect
def bind_trace_id_on_worker(task_id=None, task=None, **kwargs):
    try:
        tid = getattr(task.request, "headers", {}).get("trace_id")
        if tid:
            trace_id_ctx.set(tid)
    except Exception:
        pass
