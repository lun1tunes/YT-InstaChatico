"""Google OAuth callback handler for YouTube Data API."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])


@router.get("/callback")
async def google_oauth_callback(
    code: str = Query(..., description="Authorization code returned by Google"),
    state: Optional[str] = Query(None, description="Opaque state value returned by Google"),
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
    # Preserve state in response for caller correlation (if provided)
    if state is not None:
        token_data["state"] = state

    logger.info("OAuth token exchange succeeded | contains_refresh=%s", "refresh_token" in token_data)
    return token_data
