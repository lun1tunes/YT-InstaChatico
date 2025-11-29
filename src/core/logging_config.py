import os
import logging
import contextvars
from datetime import datetime
from logging.config import dictConfig
from typing import Optional

from core.services.telegram_alert_service import TelegramAlertService


class ChannelAliasFilter(logging.Filter):
    """Adds a friendly channel name to log records.

    Example mappings:
    - uvicorn.error -> uvicorn
    - celery.app.trace -> celery
    Other names pass through unchanged.
    """

    NAME_MAP = {
        "uvicorn.error": "uvicorn",
        "uvicorn.access": "uvicorn.access",
        "celery.app.trace": "celery",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        record.channel = self.NAME_MAP.get(record.name, record.name)
        return True


# Trace context
trace_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_ctx.get() or "-"
        return True


class TelegramLogHandler(logging.Handler):
    """Simplified handler using TelegramAlertService for log alerts."""

    def __init__(self, level: int = logging.WARNING, alert_service: Optional[TelegramAlertService] = None):
        super().__init__(level)
        self._service = alert_service

    def emit(self, record: logging.LogRecord) -> None:
        """Send log message to Telegram LOGS thread."""
        try:
            trace_id = getattr(record, "trace_id", "-")
            timestamp = datetime.utcfromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
            message = self.format(record)
            exception_text = self.formatException(record.exc_info) if record.exc_info else None

            # Build log data
            log_data = {
                "level": record.levelname,
                "logger": record.name,
                "trace_id": trace_id,
                "timestamp": timestamp,
                "message": message,
                "exception": exception_text,
            }

            # Use async service in sync context (create new event loop if needed)
            import asyncio

            if self._service:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, create task (fire and forget)
                        asyncio.create_task(self._service.send_log_alert(log_data))
                    else:
                        # If no loop running, run until complete
                        loop.run_until_complete(self._service.send_log_alert(log_data))
                except RuntimeError:
                    # No event loop, create new one
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self._service.send_log_alert(log_data))
                    loop.close()

        except Exception:
            # Never raise from logging handler
            pass


def _resolve_log_level(default: str = "INFO") -> str:
    # Single source of truth: LOGS_LEVEL
    env_level = os.getenv("LOGS_LEVEL", "").strip().upper()
    if env_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return env_level
    return default


def configure_logging() -> None:
    """Configure application-wide logging using stdlib logging.

    - Single console handler suitable for Dozzle (plain text, no JSON)
    - Unify levels across app, uvicorn and celery
    - Keep existing loggers (disable_existing_loggers=False)
    """
    level = _resolve_log_level()

    # Obtain shared infrastructure instances from the container
    log_alert_handler_config = {
        "class": "core.logging_config.TelegramLogHandler",
        "level": "WARNING",
    }

    try:
        from core.container import get_container

        container = get_container()
        alert_service = container.log_alert_service()
        log_alert_handler_config["alert_service"] = alert_service
    except Exception:
        logging.getLogger(__name__).debug("Log alert service unavailable; Telegram log handler will be inert.")

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "channel": {"()": "core.logging_config.ChannelAliasFilter"},
            "trace": {"()": "core.logging_config.TraceIdFilter"},
        },
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)-8s | %(channel)-20s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "with_trace": {
                "format": "%(asctime)s | %(levelname)-8s | %(channel)-20s | [%(trace_id)s] | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            # Uvicorn access logs are very chatty; keep them concise
            "uvicorn_access": {
                "format": "%(asctime)s | %(levelname)-8s | %(channel)-20s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "with_trace" if level == "DEBUG" else "default",
                "level": level,
                "stream": "ext://sys.stdout",
                "filters": ["channel", "trace"],
            },
            "uvicorn_console": {
                "class": "logging.StreamHandler",
                "formatter": "uvicorn_access",
                "level": ("INFO" if level == "DEBUG" else level),  # Reduce uvicorn access verbosity in DEBUG
                "stream": "ext://sys.stdout",
                "filters": ["channel", "trace"],
            },
            "telegram_alerts": log_alert_handler_config,
        },
        "loggers": {
            # App-level
            "": {  # root
                "handlers": ["console", "telegram_alerts"],
                "level": level,
            },
            # Uvicorn loggers
            "uvicorn": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["uvicorn_console"],
                "level": level,
                "propagate": False,
            },
            # Celery loggers
            "celery": {
                "handlers": ["console", "telegram_alerts"],
                "level": level,
                "propagate": False,
            },
            "celery.app.trace": {
                "handlers": ["console", "telegram_alerts"],
                "level": level,
                "propagate": False,
            },
            "celery.pool": {
                "handlers": ["console"],
                "level": "WARNING",  # Suppress verbose DEBUG task pool logs
                "propagate": False,
            },
            "celery.bootsteps": {
                "handlers": ["console"],
                "level": "WARNING",  # Suppress verbose DEBUG worker startup logs
                "propagate": False,
            },
            "celery.utils.functional": {
                "handlers": ["console"],
                "level": "WARNING",  # Suppress very verbose task introspection logs
                "propagate": False,
            },
            "celery.worker": {
                "handlers": ["console"],
                "level": "INFO",  # Worker state changes are useful
                "propagate": False,
            },
            # SQLAlchemy warnings/errors (DB constraint violations, etc.)
            "sqlalchemy": {
                "handlers": ["console", "telegram_alerts"],
                "level": "WARNING",
                "propagate": False,
            },
            # Suppress noisy third-party libraries in non-DEBUG mode
            "agents": {
                "handlers": ["console"],
                "level": level if level == "DEBUG" else "WARNING",
                "propagate": False,
            },
            "openai": {
                "handlers": ["console"],
                "level": "WARNING",  # Always suppress OpenAI verbose logs
                "propagate": False,
            },
            "openai._base_client": {
                "handlers": ["console"],
                "level": "WARNING",  # Suppress verbose request/response logs with large payloads
                "propagate": False,
            },
            "httpx": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }

    # Optionally disable telegram alerts via env flag
    if os.getenv("DISABLE_TELEGRAM_LOG_ALERTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        # Remove telegram handler from root logger
        try:
            config["loggers"][""]["handlers"].remove("telegram_alerts")
        except Exception:
            pass

    dictConfig(config)
    logging.getLogger(__name__).debug("Logging configured with level %s", level)
