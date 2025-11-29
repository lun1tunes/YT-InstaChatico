"""
Telegram API endpoints for testing and management
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from core.logging_config import trace_id_ctx
from core.container import get_container, Container

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Telegram"])


@router.get("/test-connection")
async def test_telegram_bot_connection(
    container: Container = Depends(get_container),
):
    """Test Telegram bot connection and configuration"""
    try:
        telegram_service = container.telegram_service()
        result = await telegram_service.test_connection()

        if result.get("success"):
            return {
                "status": "success",
                "message": "Telegram bot connection successful",
                "bot_info": result.get("bot_info"),
                "chat_id": result.get("chat_id"),
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Telegram connection failed: {result.get('error')}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing Telegram connection: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/test-notification")
async def test_telegram_notification(
    container: Container = Depends(get_container),
):
    """Send a test notification to Telegram"""
    try:
        # Create test comment data
        test_comment_data = {
            "comment_id": "test_12345",
            "comment_text": "This is a test urgent issue comment for testing Telegram notifications.",
            "classification": "urgent issue / complaint",
            "confidence": 95,
            "reasoning": "Test notification to verify Telegram integration is working correctly.",
            "sentiment_score": -80,
            "toxicity_score": 20,
            "media_id": "test_media_123",
            "username": "test_user",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        telegram_service = container.telegram_service()
        result = await telegram_service.send_urgent_issue_notification(test_comment_data)

        if result.get("success"):
            return {
                "status": "success",
                "message": "Test notification sent successfully",
                "telegram_message_id": result.get("message_id"),
                "response": result.get("response"),
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to send test notification: {result.get('error')}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/test-log-alert")
async def test_log_alert(level: str = "warning"):
    """Emit a test log at the given level to verify Telegram log alerts.
    Levels: debug, info, warning, error, critical
    """
    level = level.lower().strip()
    trace_id = trace_id_ctx.get()

    if level == "debug":
        logger.debug("🔍 Test log alert: DEBUG level")
    elif level == "info":
        logger.info("ℹ️ Test log alert: INFO level")
    elif level == "warning":
        logger.warning("⚠️ Test log alert: WARNING level - should go to Telegram LOGS thread")
    elif level == "error":
        logger.error("🔴 Test log alert: ERROR level - should go to Telegram LOGS thread")
    elif level == "critical":
        logger.critical("🚨 Test log alert: CRITICAL level - should go to Telegram LOGS thread")
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid level. Use: debug|info|warning|error|critical",
        )

    return {"status": "emitted", "level": level, "trace_id": trace_id}
