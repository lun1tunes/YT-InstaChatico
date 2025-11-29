"""
Unit tests for CeleryTaskQueue.

Tests cover:
- Task enqueueing with various parameters
- Countdown/delay functionality
- Trace ID propagation
- Batch task enqueueing
- Error handling and logging
- Celery app integration
"""

import pytest
from unittest.mock import MagicMock, patch, call
from contextvars import ContextVar

from core.infrastructure.task_queue import CeleryTaskQueue


@pytest.mark.unit
@pytest.mark.infrastructure
class TestCeleryTaskQueue:
    """Test CeleryTaskQueue implementation."""

    @pytest.fixture
    def mock_celery_app(self):
        """Create a mock Celery app."""
        celery_app = MagicMock()
        # Mock AsyncResult with id attribute
        mock_result = MagicMock()
        mock_result.id = "task-id-123"
        celery_app.send_task.return_value = mock_result
        return celery_app

    @pytest.fixture
    def task_queue(self, mock_celery_app):
        """Create a CeleryTaskQueue instance with mocked Celery app."""
        return CeleryTaskQueue(celery_app=mock_celery_app)

    def test_init(self, mock_celery_app):
        """Test CeleryTaskQueue initialization."""
        # Act
        queue = CeleryTaskQueue(celery_app=mock_celery_app)

        # Assert
        assert queue.celery_app is mock_celery_app

    def test_enqueue_basic_task(self, task_queue, mock_celery_app):
        """Test enqueueing a basic task without countdown or trace_id."""
        # Arrange
        task_name = "core.tasks.classification_tasks.classify_comment_task"
        comment_id = "comment_123"

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None  # No trace ID
            task_id = task_queue.enqueue(task_name, comment_id)

        # Assert
        assert task_id == "task-id-123"
        mock_celery_app.send_task.assert_called_once_with(
            task_name,
            args=(comment_id,),
            kwargs={},
            headers=None,  # No trace_id
        )

    def test_enqueue_task_with_kwargs(self, task_queue, mock_celery_app):
        """Test enqueueing a task with keyword arguments."""
        # Arrange
        task_name = "core.tasks.answer_tasks.generate_answer_task"
        comment_id = "comment_123"
        retry_count = 2

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None
            task_id = task_queue.enqueue(
                task_name, comment_id, retry_count=retry_count
            )

        # Assert
        assert task_id == "task-id-123"
        mock_celery_app.send_task.assert_called_once_with(
            task_name,
            args=(comment_id,),
            kwargs={"retry_count": retry_count},
            headers=None,
        )

    def test_enqueue_task_with_countdown(self, task_queue, mock_celery_app):
        """Test enqueueing a task with countdown delay."""
        # Arrange
        task_name = "core.tasks.telegram_tasks.send_telegram_alert_task"
        message = "Test alert"
        countdown = 60

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None
            task_id = task_queue.enqueue(task_name, message, countdown=countdown)

        # Assert
        assert task_id == "task-id-123"
        mock_celery_app.send_task.assert_called_once_with(
            task_name,
            args=(message,),
            kwargs={},
            headers=None,
            countdown=countdown,
        )

    def test_enqueue_task_with_trace_id(self, task_queue, mock_celery_app):
        """Test enqueueing a task with trace_id for request tracking."""
        # Arrange
        task_name = "core.tasks.media_tasks.process_media_task"
        media_id = "media_456"
        trace_id = "trace-abc-123"

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = trace_id
            task_id = task_queue.enqueue(task_name, media_id)

        # Assert
        assert task_id == "task-id-123"
        mock_celery_app.send_task.assert_called_once_with(
            task_name,
            args=(media_id,),
            kwargs={},
            headers={"trace_id": trace_id},
        )

    def test_enqueue_task_with_all_parameters(self, task_queue, mock_celery_app):
        """Test enqueueing a task with all parameters: args, kwargs, countdown, trace_id."""
        # Arrange
        task_name = "core.tasks.document_tasks.process_document_task"
        document_id = "doc_789"
        user_id = "user_123"
        priority = "high"
        countdown = 30
        trace_id = "trace-xyz-456"

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = trace_id
            task_id = task_queue.enqueue(
                task_name, document_id, user_id, priority=priority, countdown=countdown
            )

        # Assert
        assert task_id == "task-id-123"
        mock_celery_app.send_task.assert_called_once_with(
            task_name,
            args=(document_id, user_id),
            kwargs={"priority": priority},
            headers={"trace_id": trace_id},
            countdown=countdown,
        )

    def test_enqueue_task_exception_handling(self, task_queue, mock_celery_app):
        """Test that enqueue re-raises exceptions from Celery."""
        # Arrange
        task_name = "core.tasks.invalid_task"
        mock_celery_app.send_task.side_effect = Exception("Connection to broker failed")

        # Act & Assert
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None
            with pytest.raises(Exception) as exc_info:
                task_queue.enqueue(task_name)

        assert "Connection to broker failed" in str(exc_info.value)
        mock_celery_app.send_task.assert_called_once()

    def test_enqueue_task_logs_error_on_exception(
        self, task_queue, mock_celery_app, caplog
    ):
        """Test that enqueue logs errors when task enqueueing fails."""
        # Arrange
        task_name = "core.tasks.failing_task"
        error_message = "Broker connection timeout"
        mock_celery_app.send_task.side_effect = Exception(error_message)

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = "trace-123"
            with pytest.raises(Exception):
                task_queue.enqueue(task_name, "arg1")

        # Assert - check that error was logged
        assert "Failed to enqueue task" in caplog.text
        assert task_name in caplog.text

    def test_enqueue_batch_empty_list(self, task_queue):
        """Test enqueueing an empty batch returns empty list."""
        # Act
        task_ids = task_queue.enqueue_batch([])

        # Assert
        assert task_ids == []

    def test_enqueue_batch_single_task(self, task_queue, mock_celery_app):
        """Test enqueueing a batch with a single task."""
        # Arrange
        tasks = [
            {
                "name": "core.tasks.classification_tasks.classify_comment_task",
                "args": ("comment_1",),
            }
        ]

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None
            task_ids = task_queue.enqueue_batch(tasks)

        # Assert
        assert len(task_ids) == 1
        assert task_ids[0] == "task-id-123"
        mock_celery_app.send_task.assert_called_once()

    def test_enqueue_batch_multiple_tasks(self, task_queue, mock_celery_app):
        """Test enqueueing a batch with multiple tasks."""
        # Arrange
        mock_results = [MagicMock(id=f"task-{i}") for i in range(3)]
        mock_celery_app.send_task.side_effect = mock_results

        tasks = [
            {
                "name": "core.tasks.classification_tasks.classify_comment_task",
                "args": ("comment_1",),
            },
            {
                "name": "core.tasks.answer_tasks.generate_answer_task",
                "args": ("comment_2",),
                "kwargs": {"retry_count": 1},
            },
            {
                "name": "core.tasks.telegram_tasks.send_telegram_alert_task",
                "args": ("message",),
                "countdown": 60,
            },
        ]

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None
            task_ids = task_queue.enqueue_batch(tasks)

        # Assert
        assert len(task_ids) == 3
        assert task_ids == ["task-0", "task-1", "task-2"]
        assert mock_celery_app.send_task.call_count == 3

        # Verify first task call
        first_call = mock_celery_app.send_task.call_args_list[0]
        assert first_call[0][0] == "core.tasks.classification_tasks.classify_comment_task"
        assert first_call[1]["args"] == ("comment_1",)

        # Verify second task call (with kwargs)
        second_call = mock_celery_app.send_task.call_args_list[1]
        assert second_call[0][0] == "core.tasks.answer_tasks.generate_answer_task"
        assert second_call[1]["kwargs"] == {"retry_count": 1}

        # Verify third task call (with countdown)
        third_call = mock_celery_app.send_task.call_args_list[2]
        assert third_call[0][0] == "core.tasks.telegram_tasks.send_telegram_alert_task"
        assert third_call[1]["countdown"] == 60

    def test_enqueue_batch_with_missing_optional_fields(
        self, task_queue, mock_celery_app
    ):
        """Test enqueueing batch tasks with missing optional fields (args, kwargs, countdown)."""
        # Arrange
        mock_results = [MagicMock(id=f"task-{i}") for i in range(2)]
        mock_celery_app.send_task.side_effect = mock_results

        tasks = [
            {
                "name": "core.tasks.health_tasks.health_check_task",
                # No args, kwargs, or countdown
            },
            {
                "name": "core.tasks.media_tasks.process_media_task",
                "args": ("media_1",),
                # No kwargs or countdown
            },
        ]

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None
            task_ids = task_queue.enqueue_batch(tasks)

        # Assert
        assert len(task_ids) == 2
        assert mock_celery_app.send_task.call_count == 2

        # Verify first call uses empty tuple for args
        first_call = mock_celery_app.send_task.call_args_list[0]
        assert first_call[1]["args"] == ()
        assert first_call[1]["kwargs"] == {}

    def test_enqueue_batch_partial_failure(self, task_queue, mock_celery_app):
        """Test that enqueue_batch propagates exceptions from individual tasks."""
        # Arrange
        mock_results = [
            MagicMock(id="task-1"),
            Exception("Task 2 failed"),  # Second task fails
        ]
        mock_celery_app.send_task.side_effect = mock_results

        tasks = [
            {"name": "task1", "args": ("arg1",)},
            {"name": "task2", "args": ("arg2",)},
        ]

        # Act & Assert
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None
            with pytest.raises(Exception) as exc_info:
                task_queue.enqueue_batch(tasks)

        assert "Task 2 failed" in str(exc_info.value)
        # First task should have been enqueued successfully
        assert mock_celery_app.send_task.call_count == 2

    def test_enqueue_countdown_none_not_passed_to_celery(
        self, task_queue, mock_celery_app
    ):
        """Test that countdown=None is not passed to Celery as a parameter."""
        # Arrange
        task_name = "core.tasks.test_task"

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None
            task_queue.enqueue(task_name, countdown=None)

        # Assert - countdown should NOT be in the call
        call_kwargs = mock_celery_app.send_task.call_args[1]
        assert "countdown" not in call_kwargs

    def test_enqueue_logs_success(self, task_queue, mock_celery_app, caplog):
        """Test that successful task enqueue is logged."""
        # Arrange
        task_name = "core.tasks.test_task"
        trace_id = "trace-456"

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = trace_id
            with caplog.at_level("INFO"):
                task_queue.enqueue(task_name, "arg1")

        # Assert
        assert "Task enqueued" in caplog.text
        assert task_name in caplog.text
        assert trace_id in caplog.text

    def test_enqueue_batch_logs_count(self, task_queue, mock_celery_app, caplog):
        """Test that enqueue_batch logs the number of tasks enqueued."""
        # Arrange
        mock_celery_app.send_task.return_value = MagicMock(id="task-id")
        tasks = [
            {"name": "task1", "args": ()},
            {"name": "task2", "args": ()},
            {"name": "task3", "args": ()},
        ]

        # Act
        with patch("core.infrastructure.task_queue.trace_id_ctx") as mock_trace_ctx:
            mock_trace_ctx.get.return_value = None
            with caplog.at_level("INFO"):
                task_queue.enqueue_batch(tasks)

        # Assert
        assert "Enqueued 3 tasks in batch" in caplog.text
