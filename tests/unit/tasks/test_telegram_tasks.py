"""Unit tests for telegram Celery tasks."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock

import pytest
from celery.exceptions import Retry

from core.tasks import telegram_tasks as tasks
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
    telegram_use_case: Any

    def __post_init__(self):
        self.sessions: List[Any] = []

    def send_telegram_notification_use_case(self, *, session):
        self.sessions.append(session)
        return self.telegram_use_case


def _patch_common(monkeypatch, container: DummyContainer, session_obj: Any):
    monkeypatch.setattr(tasks, "get_container", lambda: container)

    @asynccontextmanager
    async def _session_ctx():
        yield session_obj

    monkeypatch.setattr(tasks, "get_db_session", _session_ctx)


def _run_telegram_task(task: DummyTask, *args, **kwargs):
    run_func = tasks.send_telegram_notification_task.run.__func__
    try:
        return run_func(task, *args, **kwargs)
    finally:
        _close_worker_event_loop()


def _make_use_case(result=None, *, side_effect=None):
    execute = AsyncMock(return_value=result)
    if side_effect is not None:
        execute.side_effect = side_effect
    return SimpleNamespace(execute=execute)


def test_telegram_task_success(monkeypatch):
    use_case = _make_use_case({"status": "success"})
    container = DummyContainer(telegram_use_case=use_case)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_telegram_task(task, "c1")

    assert result == {"status": "success"}
    use_case.execute.assert_awaited_once_with("c1")


def test_telegram_task_retry(monkeypatch):
    use_case = _make_use_case({"status": "retry"})
    container = DummyContainer(telegram_use_case=use_case)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask(retries=1, max_retries=MAX_RETRIES)
    with pytest.raises(Retry):
        _run_telegram_task(task, "c1")

    assert task.retry_calls[0]["kwargs"]["countdown"] == get_retry_delay(1)


def test_telegram_task_retry_limit(monkeypatch):
    retry_result = {"status": "retry"}
    use_case = _make_use_case(retry_result)
    container = DummyContainer(telegram_use_case=use_case)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask(retries=MAX_RETRIES, max_retries=MAX_RETRIES)
    result = _run_telegram_task(task, "c1")

    assert result is retry_result
    assert task.retry_calls == []


def test_telegram_task_propagates_exception(monkeypatch):
    use_case = _make_use_case(side_effect=RuntimeError("boom"))
    container = DummyContainer(telegram_use_case=use_case)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    with pytest.raises(RuntimeError):
        _run_telegram_task(task, "c1")
