import pytest
from httpx import AsyncClient

from core.models.media import Media
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers


class _DummyContent:
    def __init__(self, data: bytes):
        self._data = data

    async def iter_chunked(self, size: int):
        yield self._data


class _DummyResponse:
    def __init__(self, status=200, headers=None, data=b"binary-image"):
        self.status = status
        self.headers = headers or {"Content-Type": "image/jpeg", "Cache-Control": "public, max-age=60"}
        self.content = _DummyContent(data)
        self._data = data
        self._released = False
        self._closed = False

    async def release(self):
        self._released = True

    async def text(self):
        return "error"

    def close(self):
        self._closed = True


class _DummyClientSession:
    def __init__(self, response: _DummyResponse):
        self._response = response
        self.closed = False

    async def get(self, url: str):
        self.requested_url = url
        return self._response

    async def close(self):
        self.closed = True


class _FailingClientSession(_DummyClientSession):
    async def get(self, url: str):
        self.requested_url = url
        return self._response


@pytest.mark.asyncio
async def test_proxy_media_image_success(integration_environment, monkeypatch):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_proxy_success",
            permalink="https://instagram.com/p/example",
            media_url="https://scontent.cdninstagram.com/test-image.jpg",
            media_type="IMAGE",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    dummy_response = _DummyResponse(data=b"image-bytes")
    dummy_session = _DummyClientSession(dummy_response)
    monkeypatch.setattr("core.services.media_proxy_service.aiohttp.ClientSession", lambda *a, **kw: dummy_session)

    response = await client.get(
        "/api/v1/media/media_proxy_success/image",
        headers=auth_headers(integration_environment),
    )

    assert response.status_code == 200
    assert response.content == b"image-bytes"
    assert response.headers["content-type"].startswith("image/")
    assert response.headers.get("cache-control") == "public, max-age=60"
    assert dummy_session.closed is True
    assert dummy_response._released is True


@pytest.mark.asyncio
async def test_proxy_media_image_invalid_host(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_proxy_invalid_host",
            permalink="https://instagram.com/p/example",
            media_url="https://example.com/not-allowed.jpg",
            media_type="IMAGE",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.get(
        "/api/v1/media/media_proxy_invalid_host/image",
        headers=auth_headers(integration_environment),
    )

    assert response.status_code == 400
    assert response.json()["meta"]["error"]["code"] == 4004


@pytest.mark.asyncio
async def test_proxy_media_image_upstream_error(integration_environment, monkeypatch):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_proxy_upstream_error",
            permalink="https://instagram.com/p/example",
            media_url="https://scontent.cdninstagram.com/fail.jpg",
            media_type="IMAGE",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    failing_response = _DummyResponse(status=500)
    failing_session = _FailingClientSession(failing_response)
    monkeypatch.setattr("core.services.media_proxy_service.aiohttp.ClientSession", lambda *a, **kw: failing_session)

    response = await client.get(
        "/api/v1/media/media_proxy_upstream_error/image",
        headers=auth_headers(integration_environment),
    )

    assert response.status_code == 502
    body = response.json()
    assert body["meta"]["error"]["code"] == 5003
