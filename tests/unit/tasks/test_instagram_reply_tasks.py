"""Unit tests for Instagram Celery tasks."""

from __future__ import annotations

from contextlib import asynccontextmanager
import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock

import pytest
from celery.exceptions import Retry

from core.tasks import instagram_reply_tasks as tasks
from core.utils.task_helpers import _close_worker_event_loop, DEFAULT_RETRY_SCHEDULE, get_retry_delay


MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)


class DummyTask:
    """Lightweight stand-in for the bound Celery task instance."""

    def __init__(self, *, retries: int = 0, max_retries: int = MAX_RETRIES, task_id: str = "task-1"):
        self.request = SimpleNamespace(id=task_id, retries=retries)
        self.max_retries = max_retries
        self.retry_calls: List[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def retry(self, *args, **kwargs):
        """Record retry arguments then raise Celery's Retry exception."""
        self.retry_calls.append((args, kwargs))
        raise Retry("retry requested")


@dataclass
class DummyContainer:
    """Container double that captures provided sessions."""

    send_use_case: Optional[AsyncMock] = None
    hide_use_case: Optional[AsyncMock] = None

    def __post_init__(self):
        self.send_sessions: List[Any] = []
        self.hide_sessions: List[Any] = []

    def send_reply_use_case(self, *, session):
        self.send_sessions.append(session)
        return self.send_use_case

    def hide_comment_use_case(self, *, session):
        self.hide_sessions.append(session)
        return self.hide_use_case


class DummyLockManager:
    """Lock manager double to control acquisition outcome."""

    def __init__(self, acquired: bool):
        self._acquired = acquired
        self.keys: List[str] = []

    @asynccontextmanager
    async def acquire(self, key: str):
        self.keys.append(key)
        yield self._acquired


def _patch_common_dependencies(monkeypatch, lock_acquired: bool, container: DummyContainer, session_obj: Any):
    lock = DummyLockManager(lock_acquired)
    monkeypatch.setattr(tasks, "lock_manager", lock)
    monkeypatch.setattr(tasks, "get_container", lambda: container)

    @asynccontextmanager
    async def _session_ctx():
        yield session_obj

    monkeypatch.setattr(tasks, "get_db_session", _session_ctx)
    return lock


def _run_send_task(task: DummyTask, *args, **kwargs):
    """Execute the send reply task using a dummy task instance."""
    run_func = tasks.send_instagram_reply_task.run.__func__
    try:
        return run_func(task, *args, **kwargs)
    finally:
        _close_worker_event_loop()


def _run_hide_task(task: DummyTask, *args, **kwargs):
    """Execute the hide comment task using a dummy task instance."""
    run_func = tasks.hide_instagram_comment_task.run.__func__
    try:
        return run_func(task, *args, **kwargs)
    finally:
        _close_worker_event_loop()


def _make_use_case(result=None, *, side_effect=None):
    execute = AsyncMock(return_value=result)
    if side_effect is not None:
        execute.side_effect = side_effect
    return SimpleNamespace(execute=execute)


def test_send_reply_skips_when_lock_held(monkeypatch):
    container = DummyContainer()
    session_obj = object()
    lock = _patch_common_dependencies(monkeypatch, lock_acquired=False, container=container, session_obj=session_obj)

    task = DummyTask()
    result = _run_send_task(task, "c1")

    assert result == {"status": "skipped", "reason": "already_processing"}
    assert lock.keys == ["instagram_reply_lock:c1"]
    assert container.send_sessions == []


def test_send_reply_success(monkeypatch):
    use_case = _make_use_case({"status": "success", "reply_id": "r1"})
    container = DummyContainer(send_use_case=use_case)
    session_obj = object()
    _patch_common_dependencies(monkeypatch, lock_acquired=True, container=container, session_obj=session_obj)

    task = DummyTask()
    result = _run_send_task(task, "c1")

    assert result == {"status": "success", "reply_id": "r1"}
    use_case.execute.assert_awaited_once_with(comment_id="c1", reply_text=None, use_generated_answer=True)
    assert container.send_sessions == [session_obj]


def test_send_reply_retries_with_countdown(monkeypatch):
    use_case = _make_use_case({"status": "retry", "retry_after": 12.3})
    container = DummyContainer(send_use_case=use_case)
    session_obj = object()
    _patch_common_dependencies(monkeypatch, lock_acquired=True, container=container, session_obj=session_obj)

    task = DummyTask(retries=1, max_retries=MAX_RETRIES)

    with pytest.raises(Retry):
        _run_send_task(task, "c1")

    assert use_case.execute.await_count == 1
    expected_delay = max(int(math.ceil(12.3)), get_retry_delay(1))
    assert task.retry_calls[0][1]["countdown"] == expected_delay  # fallback schedule if longer


def test_send_reply_returns_when_max_retries_reached(monkeypatch):
    retry_result = {"status": "retry", "retry_after": 5}
    use_case = _make_use_case(retry_result)
    container = DummyContainer(send_use_case=use_case)
    session_obj = object()
    _patch_common_dependencies(monkeypatch, lock_acquired=True, container=container, session_obj=session_obj)

    task = DummyTask(retries=MAX_RETRIES, max_retries=MAX_RETRIES)
    result = _run_send_task(task, "c1")

    assert result == retry_result
    assert task.retry_calls == []


def test_send_reply_propagates_exceptions(monkeypatch):
    use_case = _make_use_case(side_effect=ValueError("boom"))
    container = DummyContainer(send_use_case=use_case)
    session_obj = object()
    _patch_common_dependencies(monkeypatch, lock_acquired=True, container=container, session_obj=session_obj)

    task = DummyTask()
    with pytest.raises(ValueError):
        _run_send_task(task, "c1")


def test_hide_comment_skips_when_lock_held(monkeypatch):
    container = DummyContainer()
    session_obj = object()
    lock = _patch_common_dependencies(monkeypatch, lock_acquired=False, container=container, session_obj=session_obj)

    task = DummyTask()
    result = _run_hide_task(task, "c1")

    assert result == {"status": "skipped", "reason": "already_processing"}
    assert lock.keys == ["instagram_hide_lock:c1"]
    assert container.hide_sessions == []


def test_hide_comment_success(monkeypatch):
    use_case = _make_use_case({"status": "success"})
    container = DummyContainer(hide_use_case=use_case)
    session_obj = object()
    _patch_common_dependencies(monkeypatch, lock_acquired=True, container=container, session_obj=session_obj)

    task = DummyTask()
    result = _run_hide_task(task, "c1")

    assert result == {"status": "success"}
    use_case.execute.assert_awaited_once_with("c1", hide=True, initiator="ai")
    assert container.hide_sessions == [session_obj]


def test_hide_comment_retries_with_fixed_delay(monkeypatch):
    use_case = _make_use_case({"status": "retry"})
    container = DummyContainer(hide_use_case=use_case)
    session_obj = object()
    _patch_common_dependencies(monkeypatch, lock_acquired=True, container=container, session_obj=session_obj)

    task = DummyTask(retries=0, max_retries=MAX_RETRIES)

    with pytest.raises(Retry):
        _run_hide_task(task, "c1")

    assert task.retry_calls[0][1]["countdown"] == get_retry_delay(0)


def test_hide_comment_returns_when_retry_limit_hit(monkeypatch):
    result_payload = {"status": "retry"}
    use_case = _make_use_case(result_payload)
    container = DummyContainer(hide_use_case=use_case)
    session_obj = object()
    _patch_common_dependencies(monkeypatch, lock_acquired=True, container=container, session_obj=session_obj)

    task = DummyTask(retries=MAX_RETRIES, max_retries=MAX_RETRIES)
    result = _run_hide_task(task, "c1")

    assert result == result_payload
    assert task.retry_calls == []


def test_hide_comment_propagates_exceptions(monkeypatch):
    use_case = _make_use_case(side_effect=RuntimeError("failure"))
    container = DummyContainer(hide_use_case=use_case)
    session_obj = object()
    _patch_common_dependencies(monkeypatch, lock_acquired=True, container=container, session_obj=session_obj)

    task = DummyTask()
    with pytest.raises(RuntimeError):
        _run_hide_task(task, "c1")
