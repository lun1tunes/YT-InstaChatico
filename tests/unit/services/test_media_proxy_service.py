import pytest
from unittest.mock import AsyncMock

from core.services.media_proxy_service import MediaProxyService


class DummyResponse:
    class _Content:
        def __init__(self, chunks):
            self._chunks = chunks

        async def iter_chunked(self, size):
            for chunk in self._chunks:
                yield chunk

    def __init__(self, status=200, headers=None, chunks=None):
        self.status = status
        self.headers = headers or {"Content-Type": "image/png", "Cache-Control": "public"}
        self._chunks = chunks or [b"chunk"]
        self._released = False
        self._closed = False
        self.content = DummyResponse._Content(self._chunks)

    async def release(self):
        self._released = True

    def close(self):
        self._closed = True


class DummySession:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.closed = False
        self.get_calls = []

    async def get(self, url):
        self.get_calls.append(url)
        if self._error:
            raise self._error
        return self._response

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_fetch_image_success(monkeypatch):
    response = DummyResponse(chunks=[b"a", b"b"], headers={"Content-Type": "image/png", "Cache-Control": "public"})
    session = DummySession(response=response)
    monkeypatch.setattr(
        "core.services.media_proxy_service.aiohttp.ClientSession",
        lambda timeout: session,
    )

    service = MediaProxyService(timeout_seconds=10)
    result = await service.fetch_image("https://example.com/image.png")

    assert result.status == 200
    assert result.content_type == "image/png"
    assert result.cache_control == "public"

    collected = []
    async for chunk in result.iter_bytes():
        collected.append(chunk)

    assert collected == [b"a", b"b"]
    assert session.closed is True
    assert response._released is True
    assert response._closed is True


@pytest.mark.asyncio
async def test_fetch_image_propagates_error(monkeypatch):
    error = RuntimeError("boom")
    session = DummySession(error=error)
    monkeypatch.setattr(
        "core.services.media_proxy_service.aiohttp.ClientSession",
        lambda timeout: session,
    )

    service = MediaProxyService(timeout_seconds=5)

    with pytest.raises(RuntimeError):
        await service.fetch_image("https://example.com/image.png")

    assert session.closed is True


@pytest.mark.asyncio
async def test_fetch_image_close_idempotent(monkeypatch):
    response = DummyResponse(chunks=[b"content"])
    session = DummySession(response=response)
    monkeypatch.setattr(
        "core.services.media_proxy_service.aiohttp.ClientSession",
        lambda timeout: session,
    )

    service = MediaProxyService(timeout_seconds=10)
    result = await service.fetch_image("https://example.com/image.png")

    await result.close()
    await result.close()

    assert response._released is True
    assert response._closed is True
    assert session.closed is True
