"""Unit tests for Celery application configuration."""

from types import SimpleNamespace

import pytest

from core.celery_app import celery_app, add_trace_id_on_publish, bind_trace_id_on_worker
from core.logging_config import trace_id_ctx


@pytest.mark.unit
def test_celery_app_basic_configuration():
    """Validate core Celery application configuration."""
    conf = celery_app.conf

    # Identity and broker/back-end setup
    assert celery_app.main == "youtube_comment_manager"
    assert conf.broker_connection_retry_on_startup is True
    assert conf.broker_connection_retry is True
    assert conf.result_backend_transport_options["retry_on_timeout"] is True

    # Serialization and accepted content
    assert conf.task_serializer == "json"
    assert conf.accept_content == ["json"]
    assert conf.result_serializer == "json"

    # Worker logging/behavior
    assert conf.worker_hijack_root_logger is False
    assert conf.worker_redirect_stdouts_level == "WARNING"
    assert conf.worker_prefetch_multiplier == 1
    assert conf.worker_cancel_long_running_tasks_on_connection_loss is True


@pytest.mark.unit
def test_celery_app_includes_and_routes():
    """Ensure task modules are registered and routed to correct queues."""
    imports = set(celery_app.conf.include)
    expected_modules = {
        "core.tasks.classification_tasks",
        "core.tasks.answer_tasks",
        "core.tasks.instagram_reply_tasks",
        "core.tasks.telegram_tasks",
        "core.tasks.health_tasks",
        "core.tasks.media_tasks",
        "core.tasks.document_tasks",
        "core.tasks.instagram_token_tasks",
        "core.tasks.youtube_tasks",
    }
    assert expected_modules.issubset(imports)

    routes = celery_app.conf.task_routes
    assert routes["core.tasks.classification_tasks.classify_comment_task"]["queue"] == "llm_queue"
    assert routes["core.tasks.answer_tasks.generate_answer_task"]["queue"] == "llm_queue"
    assert routes["core.tasks.instagram_reply_tasks.send_instagram_reply_task"]["queue"] == "instagram_queue"
    assert routes["core.tasks.instagram_reply_tasks.hide_instagram_comment_task"]["queue"] == "instagram_queue"
    assert routes["core.tasks.youtube_tasks.poll_youtube_comments_task"]["queue"] == "youtube_queue"
    assert routes["core.tasks.youtube_tasks.send_youtube_reply_task"]["queue"] == "youtube_queue"
    assert routes["core.tasks.youtube_tasks.delete_youtube_comment_task"]["queue"] == "youtube_queue"


@pytest.mark.unit
def test_celery_app_beat_schedule():
    """Validate Celery beat schedule entries."""
    beat_schedule = celery_app.conf.beat_schedule

    assert "retry-failed-classifications" in beat_schedule
    retry_entry = beat_schedule["retry-failed-classifications"]
    assert retry_entry["task"] == "core.tasks.classification_tasks.retry_failed_classifications"

    assert "check-system-health" in beat_schedule
    health_entry = beat_schedule["check-system-health"]
    assert health_entry["task"] == "core.tasks.health_tasks.check_system_health_task"

    assert "check-instagram-token-expiration" not in beat_schedule
    assert "poll-youtube-comments" in beat_schedule
    youtube_entry = beat_schedule["poll-youtube-comments"]
    assert youtube_entry["task"] == "core.tasks.youtube_tasks.poll_youtube_comments_task"


@pytest.mark.unit
def test_add_trace_id_on_publish_sets_header():
    """Signal should add current trace id to Celery headers."""
    token = trace_id_ctx.set("trace-123")
    headers = {"existing": "value"}

    add_trace_id_on_publish(headers=headers)

    assert headers["trace_id"] == "trace-123"
    trace_id_ctx.reset(token)


@pytest.mark.unit
def test_add_trace_id_on_publish_preserves_existing_header():
    """Existing trace id header should not be overwritten."""
    token = trace_id_ctx.set("outer-trace")
    headers = {"trace_id": "existing"}

    add_trace_id_on_publish(headers=headers)

    assert headers["trace_id"] == "existing"
    trace_id_ctx.reset(token)


@pytest.mark.unit
def test_add_trace_id_on_publish_no_trace_id_noop():
    """When no trace id in context, headers remain unchanged."""
    token = trace_id_ctx.set(None)
    headers = {}

    add_trace_id_on_publish(headers=headers)

    assert "trace_id" not in headers
    trace_id_ctx.reset(token)


@pytest.mark.unit
def test_bind_trace_id_on_worker_sets_context():
    """Worker-side signal should bind trace id from headers."""
    token = trace_id_ctx.set(None)
    task = SimpleNamespace(request=SimpleNamespace(headers={"trace_id": "worker-trace"}))

    bind_trace_id_on_worker(task=task)

    assert trace_id_ctx.get() == "worker-trace"
    trace_id_ctx.reset(token)


@pytest.mark.unit
def test_bind_trace_id_on_worker_handles_missing_header():
    """Signal should not raise when header is absent."""
    token = trace_id_ctx.set("existing")
    task = SimpleNamespace(request=SimpleNamespace(headers={}))

    bind_trace_id_on_worker(task=task)

    # Value should remain unchanged
    assert trace_id_ctx.get() == "existing"
    trace_id_ctx.reset(token)
