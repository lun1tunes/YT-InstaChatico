"""Google OAuth callback handler for YouTube Data API."""

from __future__ import annotations

import logging
import time
import uuid
import hmac
import hashlib
import urllib.parse
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.container import get_container, Container
from core.models import db_helper
from core.services.oauth_token_service import OAuthTokenService
from .schemas import AuthUrlResponse, AccountStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",  # manage and moderate YouTube comments
]

STATE_TTL_SECONDS = 600  # 10 minutes

@router.get("/callback")
async def google_oauth_callback(
    code: str = Query(..., description="Authorization code returned by Google"),
    state: Optional[str] = Query(None, description="Opaque state value returned by Google"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> Dict[str, Any]:
    """
    Handle OAuth redirect from Google and exchange authorization code for tokens.

    The authorization server redirects the user's browser back to this endpoint with:
    - `code` (query param): short-lived authorization code
    - `state` (optional): value you supplied in the initial auth request

    This endpoint performs the server-to-server token exchange using the app's
    client credentials and returns the token payload. Credentials are never
    included in the redirect; only the authorization code is present.
    """
    token_endpoint = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": settings.youtube.client_id,
        "client_secret": settings.youtube.client_secret,
        "redirect_uri": settings.youtube.redirect_uri,
        "grant_type": "authorization_code",
    }

    logger.info("Exchanging Google OAuth code for tokens | has_state=%s", bool(state))

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(token_endpoint, data=payload)
    except httpx.HTTPError as exc:  # pragma: no cover - network errors
        logger.error("OAuth token exchange request failed | error=%s", exc)
        raise HTTPException(status_code=502, detail="Failed to contact Google token endpoint")

    if response.status_code != 200:
        logger.error(
            "OAuth token exchange failed | status=%s | body=%s",
            response.status_code,
            response.text,
        )
        raise HTTPException(status_code=400, detail="Authorization code exchange failed")

    token_data = response.json()

    if state:
        _validate_state(state)

    oauth_service: OAuthTokenService = container.oauth_token_service(session=session)

    # Fetch channel ID using the fresh access token
    channel_id = await _fetch_channel_id(token_data.get("access_token"))
    account_id = channel_id or settings.youtube.channel_id or "default"

    stored = await oauth_service.store_tokens(
        provider="google",
        account_id=account_id,
        token_response=token_data,
    )

    # Preserve state in response for caller correlation (if provided)
    if state is not None:
        stored["state"] = state

    logger.info(
        "OAuth token exchange succeeded | contains_refresh=%s | account_id=%s",
        "refresh_token" in token_data,
        stored["account_id"],
    )
    return stored


@router.get("/authorize", response_model=AuthUrlResponse)
async def google_oauth_authorize(state: Optional[str] = Query(None)) -> AuthUrlResponse:
    """
    Generate the Google OAuth authorization URL for the frontend to redirect the user.

    This endpoint constructs the consent URL with:
    - response_type=code
    - access_type=offline (so we get refresh tokens)
    - include_granted_scopes=true (incremental auth)
    - prompt=consent (ensure refresh token returned)
    - scope: YouTube comment management
    """
    generated_state = state or _generate_state()

    params = {
        "client_id": settings.youtube.client_id,
        "redirect_uri": settings.youtube.redirect_uri,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": generated_state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params, safe=":/ ")
    return AuthUrlResponse(auth_url=auth_url, state=generated_state)


def _generate_state() -> str:
    """
    Generate a signed, time-bound state token to mitigate CSRF.
    Encodes nonce:timestamp:signature with HMAC using APP_SECRET.
    """
    nonce = uuid.uuid4().hex
    ts = str(int(time.time()))
    msg = f"{nonce}:{ts}"
    sig = hmac.new(settings.app_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}:{ts}:{sig}"


def _validate_state(state: str) -> None:
    """Validate HMAC state and expiration."""
    try:
        nonce, ts, sig = state.split(":")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    msg = f"{nonce}:{ts}"
    expected_sig = hmac.new(settings.app_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=400, detail="State verification failed")

    if int(time.time()) - int(ts) > STATE_TTL_SECONDS:
        raise HTTPException(status_code=400, detail="State expired")


async def _fetch_channel_id(access_token: Optional[str]) -> Optional[str]:
    if not access_token:
        return None
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "id", "mine": "true"}
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning("Failed to fetch channel ID | status=%s | body=%s", resp.status_code, resp.text)
                return None
            data = resp.json()
            items = data.get("items") or []
            if not items:
                return None
            return items[0].get("id")
    except httpx.HTTPError as exc:
        logger.warning("HTTP error while fetching channel ID | error=%s", exc)
        return None


@router.get("/account", response_model=AccountStatusResponse)
async def google_account_status(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
):
    """Return stored Google account/channel status for UI."""
    oauth_service: OAuthTokenService = container.oauth_token_service(session=session)
    tokens = await oauth_service.get_tokens("google")
    return {
        "has_tokens": bool(tokens),
        "account_id": tokens.get("account_id") if tokens else None,
    }
