"""Unit tests for web image analyzer tool."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.agents.tools.web_image_analyzer_tool import _analyze_image_implementation


class DummyResponse:
    def __init__(self, status=200, headers=None, data=b"imagebytes"):
        self.status = status
        self.headers = headers or {"content-type": "image/png"}
        self._data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def read(self):
        return self._data


class DummySession:
    def __init__(self, response):
        self._response = response

    def get(self, *args, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_web_image_analyzer_success(monkeypatch):
    response = DummyResponse()
    session = DummySession(response)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = session
    mock_session_cm.__aexit__.return_value = None

    async_openai_cm = AsyncMock()
    async_openai_client = AsyncMock()

    fake_api_response = MagicMock()
    fake_api_response.choices = [MagicMock(message=MagicMock(content="analysis result"))]
    fake_api_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
    async_openai_client.chat.completions.create = AsyncMock(return_value=fake_api_response)
    async_openai_cm.__aenter__.return_value = async_openai_client
    async_openai_cm.__aexit__.return_value = None

    with patch("core.agents.tools.web_image_analyzer_tool.aiohttp.ClientSession", return_value=mock_session_cm), \
         patch("core.agents.tools.web_image_analyzer_tool.AsyncOpenAI", return_value=async_openai_cm), \
         patch("core.agents.tools.web_image_analyzer_tool.settings.openai.api_key", "test-key"):

        result = await _analyze_image_implementation("https://example.com/image.png", "context")

    assert result == "analysis result"
    async_openai_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_image_analyzer_handles_download_failure():
    response = DummyResponse(status=404)
    session = DummySession(response)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = session
    mock_session_cm.__aexit__.return_value = None

    with patch("core.agents.tools.web_image_analyzer_tool.aiohttp.ClientSession", return_value=mock_session_cm), \
         patch("core.agents.tools.web_image_analyzer_tool.settings.openai.api_key", "test-key"):

        result = await _analyze_image_implementation("https://example.com/missing.jpg")

    assert "Failed to download image" in result


@pytest.mark.asyncio
async def test_web_image_analyzer_handles_openai_failure():
    response = DummyResponse()
    session = DummySession(response)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = session
    mock_session_cm.__aexit__.return_value = None

    async_openai_cm = AsyncMock()
    async_openai_client = AsyncMock()
    async_openai_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("openai error"))
    async_openai_cm.__aenter__.return_value = async_openai_client
    async_openai_cm.__aexit__.return_value = None

    with patch("core.agents.tools.web_image_analyzer_tool.aiohttp.ClientSession", return_value=mock_session_cm), \
         patch("core.agents.tools.web_image_analyzer_tool.AsyncOpenAI", return_value=async_openai_cm), \
         patch("core.agents.tools.web_image_analyzer_tool.settings.openai.api_key", "test-key"):

        result = await _analyze_image_implementation("https://example.com/image.png")

    assert result.startswith("Ошибка при анализе изображения: openai error")
