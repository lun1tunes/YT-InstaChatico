"""Shared helper functions for JSON API integration tests."""

from datetime import datetime, timedelta, timezone

import jwt


def auth_headers(env):
    """Generate authorization headers for JSON API requests."""
    now = datetime.now(timezone.utc)
    expire_minutes = env["json_api_expire"]
    payload = {
        "sub": "test-user",
        "role": "admin",
        "scopes": ["me", "admin"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expire_minutes)).timestamp()),
    }
    token = jwt.encode(
        payload,
        env["json_api_secret"],
        algorithm=env["json_api_algorithm"],
    )
    return {"Authorization": f"Bearer {token}"}
