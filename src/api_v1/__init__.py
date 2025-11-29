from fastapi import APIRouter
import logging

from .comment_webhooks.views import router as webhooks_router
from .telegram.views import router as telegram_router
from .comments.views import router as comments_router

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(router=webhooks_router, prefix="/webhook")
router.include_router(router=telegram_router, prefix="/telegram")
router.include_router(router=comments_router)

# Try to load documents router (requires boto3, pdfplumber, python-docx)
try:
    from .documents.views import router as documents_router
    router.include_router(router=documents_router)
    logger.info("Document management endpoints loaded")
except ImportError as e:
    logger.warning(f"Document management endpoints not available: {e}")

from .instagram_insights.views import router as instagram_insights_router

router.include_router(instagram_insights_router)
