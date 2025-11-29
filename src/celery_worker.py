"""
Celery worker entry point that ensures all tasks are imported
"""

import sys
import logging

# Add the src directory to Python path
sys.path.insert(0, "/app/src")

# Import all task modules to ensure they are registered
import core.tasks.classification_tasks
import core.tasks.answer_tasks
import core.tasks.telegram_tasks
import core.tasks.instagram_reply_tasks
import core.tasks.youtube_tasks
import core.tasks.document_tasks
import core.tasks.media_tasks
import core.tasks.health_tasks
import core.tasks.instagram_token_tasks

# Import the celery app
from core.celery_app import celery_app
from core.logging_config import configure_logging

# Export the celery app for Celery to use
app = celery_app

# Configure logging for worker process (avoid Celery hijacking root via CLI flag)
configure_logging()
logging.getLogger(__name__).info("Celery worker logging configured")
