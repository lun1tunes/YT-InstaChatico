"""Celery tasks for monitoring Instagram access token health."""

import logging
from datetime import datetime, timezone, timedelta

from ..celery_app import celery_app
from ..container import get_container
from ..utils.task_helpers import async_task

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_WARNING_DAYS = 7


def _days_remaining(seconds: int | None) -> float | None:
    if seconds is None:
        return None
    return seconds / 86400


@celery_app.task
@async_task
async def check_instagram_token_expiration_task():
    """Check Instagram token expiration and alert if it is near expiry."""
    container = get_container()
    instagram_service = container.instagram_service()
    log_alert_service = container.log_alert_service()

    try:
        result = await instagram_service.get_token_expiration()
    except Exception as exc:
        logger.exception("Failed to check Instagram token expiration")
        await log_alert_service.send_log_alert(
            {
                "level": "ERROR",
                "logger": "instagram.token",
                "message": f"Failed to check Instagram token expiration: {exc}",
            }
        )
        return {"status": "error", "reason": str(exc)}

    if not result.get("success"):
        if result.get("error_code") == "missing_app_credentials":
            logger.info("Instagram app credentials not configured; skipping token expiration check.")
            return {"status": "skipped", "reason": "missing_app_credentials"}
        logger.warning("Unable to retrieve Instagram token expiration metadata: %s", result.get("error"))
        await log_alert_service.send_log_alert(
            {
                "level": "WARNING",
                "logger": "instagram.token",
                "message": f"Unable to retrieve Instagram token expiration metadata: {result.get('error')}",
            }
        )
        return {"status": "error", "reason": result.get("error")}

    expires_at: datetime | None = result.get("expires_at")
    expires_in_seconds: int | None = result.get("expires_in")

    if expires_at is None and expires_in_seconds is None:
        logger.warning("Instagram token expiration data missing 'expires_at' and 'expires_in'")
        return {"status": "unknown"}

    now = datetime.now(timezone.utc)
    if expires_at is None and expires_in_seconds is not None:
        expires_at = now + timedelta(seconds=expires_in_seconds)

    days_remaining = _days_remaining(expires_in_seconds)
    logger.info(
        "Instagram token expires at %s (in %s days)",
        expires_at.isoformat() if expires_at else None,
        f"{days_remaining:.2f}" if days_remaining is not None else "unknown",
    )

    alert_sent = False
    status_message = (
        f"Instagram access token health check: expires in "
        f"{days_remaining:.1f} days ({expires_at.isoformat() if expires_at else 'unknown timestamp'})."
    )

    if days_remaining is not None and days_remaining <= TOKEN_EXPIRY_WARNING_DAYS:
        message = (
            f"⚠️ Instagram access token expires in approximately {days_remaining:.1f} days "
            f"({expires_at.isoformat() if expires_at else 'unknown expiration date'}). "
            f"Generate and configure a new token to avoid downtime."
        )
        logger.warning(message)
        await log_alert_service.send_log_alert(
            {
                "level": "WARNING",
                "logger": "instagram.token",
                "message": message,
            }
        )
        alert_sent = True
    else:
        logger.info(status_message)
        await log_alert_service.send_log_alert(
            {
                "level": "INFO",
                "logger": "instagram.token",
                "message": status_message,
            }
        )

    return {
        "status": "ok",
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expires_in_seconds": expires_in_seconds,
        "alert_sent": alert_sent,
    }
