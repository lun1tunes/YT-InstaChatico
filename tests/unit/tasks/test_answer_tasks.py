"""Unit tests for answer Celery tasks."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock

import pytest
from celery.exceptions import Retry

from core.tasks import answer_tasks as tasks
from core.utils.task_helpers import _close_worker_event_loop, DEFAULT_RETRY_SCHEDULE, get_retry_delay


MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)


class DummyTask:
    def __init__(self, *, retries: int = 0, max_retries: int = MAX_RETRIES):
        self.request = SimpleNamespace(id="task-1", retries=retries)
        self.max_retries = max_retries
        self.retry_calls: List[dict[str, Any]] = []

    def retry(self, *args, **kwargs):
        self.retry_calls.append({"args": args, "kwargs": kwargs})
        raise Retry("retry requested")


@dataclass
class DummyContainer:
    answer_use_case: Any
    queue: Any

    def __post_init__(self):
        self.sessions: List[Any] = []

    def generate_answer_use_case(self, *, session):
        self.sessions.append(session)
        return self.answer_use_case

    def task_queue(self):
        return self.queue


class DummyQueue:
    def __init__(self, *, raise_error: Optional[Exception] = None):
        self.calls: List[tuple[Any, ...]] = []
        self.raise_error = raise_error

    def enqueue(self, *args):
        if self.raise_error:
            raise self.raise_error
        self.calls.append(args)
        return f"task-{len(self.calls)}"


def _patch_common(monkeypatch, container: DummyContainer, session_obj: Any):
    monkeypatch.setattr(tasks, "get_container", lambda: container)

    @asynccontextmanager
    async def _session_ctx():
        yield session_obj

    monkeypatch.setattr(tasks, "get_db_session", _session_ctx)


def _run_answer_task(task: DummyTask, *args, **kwargs):
    run_func = tasks.generate_answer_task.run.__func__
    try:
        return run_func(task, *args, **kwargs)
    finally:
        _close_worker_event_loop()


def _make_use_case(result=None, *, side_effect=None):
    execute = AsyncMock(return_value=result)
    if side_effect is not None:
        execute.side_effect = side_effect
    return SimpleNamespace(execute=execute)


def test_generate_answer_success_with_reply(monkeypatch):
    queue = DummyQueue()
    use_case = _make_use_case(
        {
            "status": "success",
            "answer": "Hello!",
            "confidence": 0.9,
            "quality_score": 0.8,
        }
    )
    container = DummyContainer(answer_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_answer_task(task, "c1")

    assert result["status"] == "success"
    use_case.execute.assert_awaited_once_with("c1", retry_count=0)
    # DB lookup failure should still route to YouTube reply task, not Instagram fallback
    assert queue.calls == [("core.tasks.youtube_tasks.send_youtube_reply_task", "c1", "Hello!")]


def test_generate_answer_success_without_answer(monkeypatch):
    queue = DummyQueue()
    use_case = _make_use_case({"status": "success", "answer": None})
    container = DummyContainer(answer_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_answer_task(task, "c1")

    assert result["status"] == "success"
    assert queue.calls == []


def test_generate_answer_success_queue_error(monkeypatch):
    queue = DummyQueue(raise_error=RuntimeError("queue down"))
    use_case = _make_use_case({"status": "success", "answer": "Hello"})
    container = DummyContainer(answer_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_answer_task(task, "c1")

    assert result["status"] == "success"
    # queue error should be swallowed
    assert queue.calls == []


def test_generate_answer_retry(monkeypatch):
    queue = DummyQueue()
    use_case = _make_use_case({"status": "retry"})
    container = DummyContainer(answer_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask(retries=1, max_retries=MAX_RETRIES)
    with pytest.raises(Retry):
        _run_answer_task(task, "c1")

    expected_delay = get_retry_delay(1)
    assert task.retry_calls[0]["kwargs"]["countdown"] == expected_delay


def test_generate_answer_retry_limit(monkeypatch):
    queue = DummyQueue()
    retry_result = {"status": "retry"}
    use_case = _make_use_case(retry_result)
    container = DummyContainer(answer_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask(retries=MAX_RETRIES, max_retries=MAX_RETRIES)
    result = _run_answer_task(task, "c1")

    assert result is retry_result
    assert task.retry_calls == []


def test_generate_answer_error(monkeypatch):
    queue = DummyQueue()
    use_case = _make_use_case({"status": "error"})
    container = DummyContainer(answer_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_answer_task(task, "c1")

    assert result["status"] == "error"
