"""Unit tests for document context agent tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agents.tools.document_context_tool import _document_context_implementation


class _AsyncSessionCtx:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_document_context_returns_formatted_output():
    session = object()
    context = "# Business Information\n\nDetails"

    with patch("core.utils.task_helpers.get_db_session", return_value=_AsyncSessionCtx(session)), \
         patch("core.agents.tools.document_context_tool.document_context_service") as mock_service:

        mock_service.get_client_context = AsyncMock(return_value=context)

        result = await _document_context_implementation()

    assert result.startswith("✅ Business Documents Context:")
    mock_service.get_client_context.assert_awaited_once_with(session=session)


@pytest.mark.asyncio
async def test_document_context_handles_missing_documents():
    session = object()

    with patch("core.utils.task_helpers.get_db_session", return_value=_AsyncSessionCtx(session)), \
         patch("core.agents.tools.document_context_tool.document_context_service") as mock_service:

        mock_service.get_client_context = AsyncMock(return_value="# Business Information")

        result = await _document_context_implementation()

    assert "NO BUSINESS DOCUMENTS AVAILABLE" in result


@pytest.mark.asyncio
async def test_document_context_handles_error():
    class ExplodingCtx(_AsyncSessionCtx):
        async def __aenter__(self):
            raise RuntimeError("db issue")

    with patch("core.utils.task_helpers.get_db_session", return_value=ExplodingCtx(None)):
        result = await _document_context_implementation()

    assert result.startswith("❌ Error retrieving business documents: db issue")
