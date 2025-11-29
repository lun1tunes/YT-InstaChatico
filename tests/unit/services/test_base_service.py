"""Unit tests for BaseService helpers."""

import pytest

from core.services.base_service import BaseService


class StubSessionService:
    def __init__(self):
        self.session = object()
        self.requested = None

    def get_session(self, conversation_id: str):
        self.requested = conversation_id
        return self.session

    async def has_messages(self, conversation_id: str) -> bool:
        raise RuntimeError("db failure")


@pytest.mark.unit
@pytest.mark.service
class TestBaseService:
    def test_sanitize_input_html_and_whitespace(self):
        raw = "  <b>Hello</b>   world!!!????   "
        sanitized = BaseService._sanitize_input(raw)
        assert sanitized == "&lt;b&gt;Hello&lt;/b&gt; world???"

    def test_estimate_tokens_floor(self):
        text = "a" * 9
        assert BaseService._estimate_tokens(text) == 2

    def test_get_session_uses_session_service(self, tmp_path):
        stub = StubSessionService()
        service = BaseService(db_path=str(tmp_path / "db.sqlite"), session_service=stub)

        session = service._get_session("conv42")

        assert session is stub.session
        assert stub.requested == "conv42"

    def test_default_session_service_initialization(self, tmp_path, monkeypatch):
        created = {}

        class FakeAgentSessionService:
            def __init__(self, db_path):
                created["db_path"] = db_path

            def get_session(self, conv_id):
                return conv_id

            async def has_messages(self, conv_id):
                return True

        from core.services import agent_session_service

        monkeypatch.setattr(
            agent_session_service,
            "AgentSessionService",
            FakeAgentSessionService,
        )

        service = BaseService(db_path=str(tmp_path / "conversations" / "db.sqlite"))

        assert isinstance(service.session_service, FakeAgentSessionService)
        assert created["db_path"].endswith("conversations/db.sqlite")

    @pytest.mark.asyncio
    async def test_session_has_messages_handles_exception(self, tmp_path):
        stub = StubSessionService()
        service = BaseService(db_path=str(tmp_path / "db.sqlite"), session_service=stub)

        result = await service._session_has_messages("conv42")

        assert result is False
