"""
Unit tests for AgentSessionService.
"""

import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import sqlite3
from agents import SQLiteSession

from core.services.agent_session_service import AgentSessionService


class DummyLoop:
    """Simple event loop stub for run_in_executor."""

    def __init__(self, result):
        self._result = result

    def run_in_executor(self, executor, func, *args):
        async def _coro():
            return func(*args)

        return _coro()


@pytest.mark.unit
@pytest.mark.service
class TestAgentSessionService:
    """Validate agent session helper behaviour."""

    @pytest.mark.asyncio
    async def test_ensure_context_injects_when_session_empty(self, tmp_path, monkeypatch):
        service = AgentSessionService(db_path=str(tmp_path / "sessions.db"))
        stub_session = SimpleNamespace(add_items=AsyncMock())

        monkeypatch.setattr(service, "get_session", lambda conversation_id: stub_session)
        monkeypatch.setattr(service, "has_messages", AsyncMock(return_value=False))

        context_items = [{"role": "system", "content": "ctx"}]
        result = await service.ensure_context("conv", context_items)

        stub_session.add_items.assert_awaited_once_with(context_items)
        assert result is stub_session

    @pytest.mark.asyncio
    async def test_ensure_context_skips_when_messages_exist(self, tmp_path, monkeypatch):
        service = AgentSessionService(db_path=str(tmp_path / "sessions.db"))
        stub_session = SimpleNamespace(add_items=AsyncMock())

        monkeypatch.setattr(service, "get_session", lambda conversation_id: stub_session)
        monkeypatch.setattr(service, "has_messages", AsyncMock(return_value=True))

        await service.ensure_context("conv", [{"role": "system", "content": "ctx"}])

        stub_session.add_items.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ensure_context_no_context_returns_session(self, tmp_path, monkeypatch):
        service = AgentSessionService(db_path=str(tmp_path / "sessions.db"))
        stub_session = SimpleNamespace(add_items=AsyncMock())

        monkeypatch.setattr(service, "get_session", lambda conversation_id: stub_session)

        result = await service.ensure_context("conv", None)
        assert result is stub_session
        stub_session.add_items.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_has_messages_uses_sync_helper(self, tmp_path, monkeypatch):
        service = AgentSessionService(db_path=str(tmp_path / "sessions.db"))

        monkeypatch.setattr(
            "core.services.agent_session_service.asyncio.get_running_loop",
            lambda: DummyLoop(True),
        )
        monkeypatch.setattr(service, "_session_has_messages_sync", lambda conversation_id: True)

        assert await service.has_messages("conv") is True

    @pytest.mark.asyncio
    async def test_session_has_messages_sync_reads_database(self, tmp_path):
        db_path = tmp_path / "conv.db"
        service = AgentSessionService(db_path=str(db_path))

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE agent_messages (session_id TEXT, content TEXT)")
        conn.execute("INSERT INTO agent_messages VALUES (?, ?)", ("conv", "hello"))
        conn.commit()
        conn.close()

        assert service._session_has_messages_sync("conv") is True
        assert service._session_has_messages_sync("missing") is False

    def test_get_session_returns_sqlite_session(self, tmp_path):
        service = AgentSessionService(db_path=str(tmp_path / "sess.db"))
        session = service.get_session("conversation")
        assert isinstance(session, SQLiteSession)

    def test_session_has_messages_sync_no_db(self, tmp_path):
        service = AgentSessionService(db_path=str(tmp_path / "missing.db"))
        assert service._session_has_messages_sync("conv") is False
