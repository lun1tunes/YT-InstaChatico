import pytest

from core.config import settings
from core.services.instagram_service import InstagramGraphAPIService


def _create_service() -> InstagramGraphAPIService:
    return InstagramGraphAPIService(access_token="user-token", session=None, rate_limiter=None)


def test_build_debug_access_token_prefers_explicit(monkeypatch):
    monkeypatch.setattr(settings.instagram, "app_access_token", "explicit-token", raising=False)
    monkeypatch.setattr(settings.instagram, "app_id", "app-id", raising=False)
    monkeypatch.setattr(settings.instagram, "app_secret", "app-secret", raising=False)

    service = _create_service()

    assert service._build_debug_access_token() == "explicit-token"


def test_build_debug_access_token_from_id_secret(monkeypatch):
    monkeypatch.setattr(settings.instagram, "app_access_token", "", raising=False)
    monkeypatch.setattr(settings.instagram, "app_id", "app-id", raising=False)
    monkeypatch.setattr(settings.instagram, "app_secret", "app-secret", raising=False)

    service = _create_service()

    assert service._build_debug_access_token() == "app-id|app-secret"


def test_build_debug_access_token_missing_config(monkeypatch):
    monkeypatch.setattr(settings.instagram, "app_access_token", "", raising=False)
    monkeypatch.setattr(settings.instagram, "app_id", "", raising=False)
    monkeypatch.setattr(settings.instagram, "app_secret", "", raising=False)

    service = _create_service()

    with pytest.raises(ValueError):
        service._build_debug_access_token()
