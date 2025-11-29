import pytest

from core.use_cases.proxy_media_image import ProxyMediaImageUseCase, MediaImageProxyError


class FakeMedia:
    def __init__(self, media_url=None, children_media_urls=None):
        self.media_url = media_url
        self.children_media_urls = children_media_urls


class FakeMediaRepository:
    def __init__(self, media_by_id):
        self._media_by_id = media_by_id
        self.requested_ids = []

    async def get_by_id(self, media_id):
        self.requested_ids.append(media_id)
        return self._media_by_id.get(media_id)


class FakeFetchResult:
    def __init__(self, status=200, content_type="image/jpeg", cache_control=None, chunks=None):
        self.status = status
        self.content_type = content_type
        self.cache_control = cache_control
        self._chunks = chunks or [b"data"]
        self.closed = False

    def iter_bytes(self):
        async def generator():
            for chunk in self._chunks:
                yield chunk
            # Simulate close responsibility on consumer
        return generator()

    async def close(self):
        self.closed = True


class FakeMediaProxyService:
    def __init__(self, fetch_result=None, error=None, sequence=None):
        self._fetch_result = fetch_result
        self._error = error
        self._sequence = list(sequence) if sequence is not None else None
        self.requested_urls = []

    async def fetch_image(self, url: str):
        self.requested_urls.append(url)
        if self._error:
            raise self._error
        if self._sequence is not None and self._sequence:
            return self._sequence.pop(0)
        return self._fetch_result


class FakeMediaService:
    def __init__(self, repository: FakeMediaRepository, refreshed_media=None):
        self.repository = repository
        self.refreshed_media = refreshed_media
        self.calls = []

    async def refresh_media_urls(self, media_id: str, session):
        self.calls.append(media_id)
        if self.refreshed_media is None:
            return None
        self.repository._media_by_id[media_id] = self.refreshed_media
        return self.refreshed_media


def repo_factory_builder(repository):
    def factory(*, session):
        return repository
    return factory


@pytest.mark.asyncio
async def test_proxy_media_image_success():
    media = FakeMedia(media_url="https://cdninstagram.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    fetch_result = FakeFetchResult(chunks=[b"a", b"b"], cache_control="public")
    proxy_service = FakeMediaProxyService(fetch_result=fetch_result)
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    result = await use_case.execute("media1")

    assert result.media_url == "https://cdninstagram.com/image.jpg"
    assert result.fetch_result is fetch_result
    assert proxy_service.requested_urls == ["https://cdninstagram.com/image.jpg"]
    assert fetch_result.closed is False


@pytest.mark.asyncio
async def test_proxy_media_image_child_index():
    media = FakeMedia(children_media_urls=["https://cdninstagram.com/child.jpg"])
    repository = FakeMediaRepository(media_by_id={"media1": media})
    fetch_result = FakeFetchResult()
    proxy_service = FakeMediaProxyService(fetch_result=fetch_result)
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    result = await use_case.execute("media1", child_index=0)
    assert proxy_service.requested_urls == ["https://cdninstagram.com/child.jpg"]
    assert result.media_url == "https://cdninstagram.com/child.jpg"


@pytest.mark.asyncio
async def test_proxy_media_image_second_child_index():
    media = FakeMedia(
        children_media_urls=[
            "https://cdninstagram.com/child0.jpg",
            "https://cdninstagram.com/child1.jpg",
        ]
    )
    repository = FakeMediaRepository(media_by_id={"media1": media})
    fetch_result = FakeFetchResult()
    proxy_service = FakeMediaProxyService(fetch_result=fetch_result)
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    result = await use_case.execute("media1", child_index=1)
    assert proxy_service.requested_urls == ["https://cdninstagram.com/child1.jpg"]
    assert result.media_url == "https://cdninstagram.com/child1.jpg"


@pytest.mark.asyncio
async def test_proxy_media_image_media_not_found():
    repository = FakeMediaRepository(media_by_id={})
    proxy_service = FakeMediaProxyService(fetch_result=FakeFetchResult())
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("missing")

    assert exc.value.status_code == 404
    assert exc.value.code == 4040


@pytest.mark.asyncio
async def test_proxy_media_image_invalid_child_index():
    media = FakeMedia(children_media_urls=["https://cdninstagram.com/child.jpg"])
    repository = FakeMediaRepository(media_by_id={"media1": media})
    proxy_service = FakeMediaProxyService(fetch_result=FakeFetchResult())
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1", child_index=2)

    assert exc.value.code == 4043


@pytest.mark.asyncio
async def test_proxy_media_image_invalid_scheme():
    media = FakeMedia(media_url="ftp://cdninstagram.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    proxy_service = FakeMediaProxyService(fetch_result=FakeFetchResult())
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1")

    assert exc.value.code == 4003


@pytest.mark.asyncio
async def test_proxy_media_image_host_not_allowed():
    media = FakeMedia(media_url="https://example.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    proxy_service = FakeMediaProxyService(fetch_result=FakeFetchResult())
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1")

    assert exc.value.code == 4004


@pytest.mark.asyncio
async def test_proxy_media_image_fetch_service_error():
    media = FakeMedia(media_url="https://cdninstagram.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    proxy_service = FakeMediaProxyService(error=RuntimeError("boom"))
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1")

    assert exc.value.code == 5005


@pytest.mark.asyncio
async def test_proxy_media_image_non_success_status():
    media = FakeMedia(media_url="https://cdninstagram.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    fetch_result = FakeFetchResult(status=404)
    proxy_service = FakeMediaProxyService(fetch_result=fetch_result)
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1")

    assert fetch_result.closed is True
    assert exc.value.code == 5003


@pytest.mark.asyncio
async def test_proxy_media_image_refresh_on_expired_url():
    original = FakeMedia(media_url="https://cdninstagram.com/expired.jpg")
    refreshed = FakeMedia(media_url="https://cdninstagram.com/new.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": original})

    proxy_service = FakeMediaProxyService(
        sequence=[FakeFetchResult(status=403), FakeFetchResult(status=200)]
    )
    media_service = FakeMediaService(repository, refreshed_media=refreshed)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    result = await use_case.execute("media1")
    assert result.media_url == "https://cdninstagram.com/new.jpg"

    assert media_service.calls == ["media1", "media1"]
    assert proxy_service.requested_urls == [
        "https://cdninstagram.com/new.jpg",
        "https://cdninstagram.com/new.jpg",
    ]


@pytest.mark.asyncio
async def test_proxy_media_image_refresh_failure():
    original = FakeMedia(media_url="https://cdninstagram.com/expired.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": original})

    proxy_service = FakeMediaProxyService(
        fetch_result=FakeFetchResult(status=403),
        sequence=[FakeFetchResult(status=403)],
    )
    media_service = FakeMediaService(repository, refreshed_media=None)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        media_service=media_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1")

    assert exc.value.code == 5003
    assert media_service.calls == ["media1", "media1"]
