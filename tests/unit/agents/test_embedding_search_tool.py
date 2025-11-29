"""Unit tests for embedding search agent tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agents.tools.embedding_search_tool import _embedding_search_implementation


class _AsyncSessionCtx:
    """Helper async context manager returning a provided object."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_embedding_search_returns_database_empty_message():
    session = object()

    mock_service_instance = MagicMock()
    mock_service_instance.search_similar_products = AsyncMock(return_value=[])
    mock_service_instance.SIMILARITY_THRESHOLD = 0.7

    mock_service_cm = MagicMock()
    mock_service_cm.__aenter__ = AsyncMock(return_value=mock_service_instance)
    mock_service_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("core.utils.task_helpers.get_db_session", return_value=_AsyncSessionCtx(session)), \
         patch("core.agents.tools.embedding_search_tool.EmbeddingService", return_value=mock_service_cm):

        result = await _embedding_search_implementation("query")

    assert "DATABASE EMPTY" in result
    mock_service_instance.search_similar_products.assert_awaited_once()
    _, kwargs = mock_service_instance.search_similar_products.await_args
    assert kwargs["limit"] == 10  # default limit 5 -> limit * 2


@pytest.mark.asyncio
async def test_embedding_search_filters_ood_results():
    session = object()
    all_results = [
        {"is_ood": False, "similarity": 0.9, "title": "A", "description": "DescA", "category": None,
         "price": None, "tags": None, "url": None},
        {"is_ood": True, "similarity": 0.4, "title": "B", "description": "DescB", "category": None,
         "price": None, "tags": None, "url": None},
    ]

    mock_service_instance = MagicMock()
    mock_service_instance.search_similar_products = AsyncMock(return_value=all_results)
    mock_service_instance.SIMILARITY_THRESHOLD = 0.7

    mock_service_cm = MagicMock()
    mock_service_cm.__aenter__ = AsyncMock(return_value=mock_service_instance)
    mock_service_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("core.utils.task_helpers.get_db_session", return_value=_AsyncSessionCtx(session)), \
         patch("core.agents.tools.embedding_search_tool.EmbeddingService", return_value=mock_service_cm):

        result = await _embedding_search_implementation("query", limit=1)

    assert "Found 1 relevant result(s)" in result
    assert "Filtered out 1 low-confidence results" in result


@pytest.mark.asyncio
async def test_embedding_search_returns_no_relevant_message_when_all_ood():
    session = object()
    ood_results = [
        {"is_ood": True, "similarity": 0.3, "title": "Irrelevant", "description": "", "category": None,
         "price": None, "tags": None, "url": None},
    ]

    mock_service_instance = MagicMock()
    mock_service_instance.search_similar_products = AsyncMock(return_value=ood_results)
    mock_service_instance.SIMILARITY_THRESHOLD = 0.7

    mock_service_cm = MagicMock()
    mock_service_cm.__aenter__ = AsyncMock(return_value=mock_service_instance)
    mock_service_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("core.utils.task_helpers.get_db_session", return_value=_AsyncSessionCtx(session)), \
         patch("core.agents.tools.embedding_search_tool.EmbeddingService", return_value=mock_service_cm):

        result = await _embedding_search_implementation("query")

    assert "NO RELEVANT PRODUCTS FOUND" in result


@pytest.mark.asyncio
async def test_embedding_search_handles_database_error_gracefully():
    session = object()

    mock_service_instance = MagicMock()
    mock_service_instance.search_similar_products = AsyncMock(side_effect=RuntimeError("db down"))
    mock_service_instance.SIMILARITY_THRESHOLD = 0.7

    mock_service_cm = MagicMock()
    mock_service_cm.__aenter__ = AsyncMock(return_value=mock_service_instance)
    mock_service_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("core.utils.task_helpers.get_db_session", return_value=_AsyncSessionCtx(session)), \
         patch("core.agents.tools.embedding_search_tool.EmbeddingService", return_value=mock_service_cm):

        result = await _embedding_search_implementation("query")

    assert "SEARCH TEMPORARILY UNAVAILABLE" in result


@pytest.mark.asyncio
async def test_embedding_search_handles_unexpected_error():
    class ExplodingCtx(_AsyncSessionCtx):
        async def __aenter__(self):
            raise RuntimeError("boom")

    with patch("core.utils.task_helpers.get_db_session", return_value=ExplodingCtx(None)):
        result = await _embedding_search_implementation("query")

    assert result.startswith("❌ Error performing embedding search: boom")
