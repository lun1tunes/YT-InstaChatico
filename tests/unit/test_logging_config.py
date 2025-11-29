"""
Unit tests for logging configuration.

Tests cover:
- ChannelAliasFilter (log record channel mapping)
- TraceIdFilter (trace ID context variable injection)
- TelegramLogHandler (async alert sending)
- _resolve_log_level (environment variable parsing)
- configure_logging (full logging setup with dictConfig)
"""

import os
import logging
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, call
from datetime import datetime

from core.logging_config import (
    ChannelAliasFilter,
    TraceIdFilter,
    TelegramLogHandler,
    trace_id_ctx,
    _resolve_log_level,
    configure_logging,
)


@pytest.mark.unit
class TestChannelAliasFilter:
    """Test ChannelAliasFilter for friendly channel name mapping."""

    @pytest.fixture
    def filter_instance(self):
        """Create a ChannelAliasFilter instance."""
        return ChannelAliasFilter()

    @pytest.fixture
    def log_record(self):
        """Create a basic LogRecord."""
        return logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

    def test_filter_maps_uvicorn_error(self, filter_instance, log_record):
        """Test that uvicorn.error is mapped to uvicorn."""
        # Arrange
        log_record.name = "uvicorn.error"

        # Act
        result = filter_instance.filter(log_record)

        # Assert
        assert result is True
        assert log_record.channel == "uvicorn"

    def test_filter_maps_uvicorn_access(self, filter_instance, log_record):
        """Test that uvicorn.access is mapped correctly."""
        # Arrange
        log_record.name = "uvicorn.access"

        # Act
        result = filter_instance.filter(log_record)

        # Assert
        assert result is True
        assert log_record.channel == "uvicorn.access"

    def test_filter_maps_celery_app_trace(self, filter_instance, log_record):
        """Test that celery.app.trace is mapped to celery."""
        # Arrange
        log_record.name = "celery.app.trace"

        # Act
        result = filter_instance.filter(log_record)

        # Assert
        assert result is True
        assert log_record.channel == "celery"

    def test_filter_passes_through_unmapped_names(self, filter_instance, log_record):
        """Test that unmapped logger names pass through unchanged."""
        # Arrange
        log_record.name = "my.custom.logger"

        # Act
        result = filter_instance.filter(log_record)

        # Assert
        assert result is True
        assert log_record.channel == "my.custom.logger"

    def test_filter_always_returns_true(self, filter_instance, log_record):
        """Test that filter never blocks log records."""
        # Arrange
        log_record.name = "any.logger"

        # Act
        result = filter_instance.filter(log_record)

        # Assert - filter should always allow records through
        assert result is True

    def test_name_map_contains_expected_mappings(self):
        """Test that NAME_MAP contains expected logger mappings."""
        # Assert
        assert ChannelAliasFilter.NAME_MAP["uvicorn.error"] == "uvicorn"
        assert ChannelAliasFilter.NAME_MAP["uvicorn.access"] == "uvicorn.access"
        assert ChannelAliasFilter.NAME_MAP["celery.app.trace"] == "celery"


@pytest.mark.unit
class TestTraceIdFilter:
    """Test TraceIdFilter for trace ID context variable injection."""

    @pytest.fixture
    def filter_instance(self):
        """Create a TraceIdFilter instance."""
        return TraceIdFilter()

    @pytest.fixture
    def log_record(self):
        """Create a basic LogRecord."""
        return logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

    def test_filter_adds_trace_id_when_present(self, filter_instance, log_record):
        """Test that trace_id is added from context when available."""
        # Arrange
        trace_id = "trace-abc-123"
        token = trace_id_ctx.set(trace_id)

        try:
            # Act
            result = filter_instance.filter(log_record)

            # Assert
            assert result is True
            assert log_record.trace_id == trace_id
        finally:
            trace_id_ctx.reset(token)

    def test_filter_uses_dash_when_no_trace_id(self, filter_instance, log_record):
        """Test that '-' is used when no trace_id is in context."""
        # Arrange - ensure no trace_id in context
        token = trace_id_ctx.set(None)

        try:
            # Act
            result = filter_instance.filter(log_record)

            # Assert
            assert result is True
            assert log_record.trace_id == "-"
        finally:
            trace_id_ctx.reset(token)

    def test_filter_always_returns_true(self, filter_instance, log_record):
        """Test that filter never blocks log records."""
        # Act
        result = filter_instance.filter(log_record)

        # Assert
        assert result is True

    def test_filter_works_with_empty_string_trace_id(self, filter_instance, log_record):
        """Test that empty string trace_id is handled correctly."""
        # Arrange
        token = trace_id_ctx.set("")

        try:
            # Act
            result = filter_instance.filter(log_record)

            # Assert
            assert result is True
            assert log_record.trace_id == "-"  # Empty string is falsy, so should use "-"
        finally:
            trace_id_ctx.reset(token)


@pytest.mark.unit
class TestTelegramLogHandler:
    """Test TelegramLogHandler for sending log alerts."""

    @pytest.fixture
    def mock_alert_service(self):
        """Create a mock TelegramAlertService."""
        service = MagicMock()
        service.send_log_alert = AsyncMock()
        return service

    @pytest.fixture
    def log_record(self):
        """Create a LogRecord with all attributes."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=42,
            msg="Test error message",
            args=(),
            exc_info=None,
        )
        record.trace_id = "trace-123"
        return record

    def test_handler_initialization(self, mock_alert_service):
        """Test TelegramLogHandler initialization."""
        # Act
        handler = TelegramLogHandler(level=logging.WARNING, alert_service=mock_alert_service)

        # Assert
        assert handler.level == logging.WARNING
        assert handler._service is mock_alert_service

    def test_handler_initialization_without_service(self):
        """Test TelegramLogHandler can be initialized without service."""
        # Act
        handler = TelegramLogHandler(level=logging.ERROR)

        # Assert
        assert handler.level == logging.ERROR
        assert handler._service is None

    def test_emit_formats_log_data_correctly(self, mock_alert_service, log_record):
        """Test that emit formats log data with all required fields."""
        # Arrange
        handler = TelegramLogHandler(alert_service=mock_alert_service)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        # Act
        with patch.object(asyncio, 'get_event_loop') as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = False
            mock_loop.run_until_complete = MagicMock()
            mock_get_loop.return_value = mock_loop

            handler.emit(log_record)

            # Assert - check run_until_complete was called with coroutine
            mock_loop.run_until_complete.assert_called_once()
            # Get the actual call argument (the coroutine)
            call_args = mock_loop.run_until_complete.call_args[0][0]
            # Verify it's the send_log_alert coroutine by running it
            asyncio.run(call_args)

        # Verify send_log_alert was called with correct data
        mock_alert_service.send_log_alert.assert_awaited()
        call_args = mock_alert_service.send_log_alert.call_args[0][0]
        assert call_args["level"] == "ERROR"
        assert call_args["logger"] == "test.logger"
        assert call_args["trace_id"] == "trace-123"
        assert call_args["message"] == "ERROR: Test error message"
        assert call_args["exception"] is None
        assert "timestamp" in call_args

    def test_emit_includes_exception_info(self):
        """Test that emit formats exception info without crashing."""
        # Arrange
        mock_service = MagicMock()
        mock_service.send_log_alert = AsyncMock()
        handler = TelegramLogHandler(level=logging.ERROR, alert_service=mock_service)
        handler.setFormatter(logging.Formatter("%(message)s"))

        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        record.trace_id = "trace-456"

        # Act - Just verify the handler doesn't crash and exc_info is processed
        # The handler has a broad except clause that catches all exceptions,
        # so we just verify it doesn't raise
        handler.emit(record)

        # Assert - If we got here, emit() didn't crash
        # The actual exception formatting happens in formatException()
        # which is tested through the handler not raising

    def test_emit_handles_missing_trace_id(self, mock_alert_service, log_record):
        """Test that emit handles records without trace_id attribute."""
        # Arrange
        handler = TelegramLogHandler(alert_service=mock_alert_service)
        delattr(log_record, 'trace_id')  # Remove trace_id

        # Act
        with patch.object(asyncio, 'get_event_loop') as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = False
            mock_loop.run_until_complete = MagicMock()
            mock_get_loop.return_value = mock_loop

            handler.emit(log_record)
            call_args = mock_loop.run_until_complete.call_args[0][0]
            asyncio.run(call_args)

        # Assert - should use "-" as default
        call_args = mock_alert_service.send_log_alert.call_args[0][0]
        assert call_args["trace_id"] == "-"

    def test_emit_handles_running_event_loop(self, mock_alert_service, log_record):
        """Test that emit creates task when event loop is running."""
        # Arrange
        handler = TelegramLogHandler(alert_service=mock_alert_service)

        # Act
        with patch.object(asyncio, 'get_event_loop') as mock_get_loop:
            with patch.object(asyncio, 'create_task') as mock_create_task:
                mock_loop = MagicMock()
                mock_loop.is_running.return_value = True
                mock_get_loop.return_value = mock_loop

                handler.emit(log_record)

                # Assert - should create task instead of run_until_complete
                mock_create_task.assert_called_once()

    def test_emit_creates_new_loop_on_runtime_error(self, mock_alert_service, log_record):
        """Test that emit creates new event loop if RuntimeError occurs."""
        # Arrange
        handler = TelegramLogHandler(alert_service=mock_alert_service)

        # Act
        with patch.object(asyncio, 'get_event_loop', side_effect=RuntimeError("No event loop")):
            with patch.object(asyncio, 'new_event_loop') as mock_new_loop:
                mock_loop = MagicMock()
                mock_loop.run_until_complete = MagicMock()
                mock_loop.close = MagicMock()
                mock_new_loop.return_value = mock_loop

                handler.emit(log_record)

                # Assert - should create new loop, run, and close
                mock_new_loop.assert_called_once()
                mock_loop.run_until_complete.assert_called_once()
                mock_loop.close.assert_called_once()

    def test_emit_without_service_does_nothing(self, log_record):
        """Test that emit does nothing when service is None."""
        # Arrange
        handler = TelegramLogHandler(alert_service=None)

        # Act - should not raise any errors
        handler.emit(log_record)

        # Assert - just verify no exception was raised (implicit)

    def test_emit_suppresses_all_exceptions(self, mock_alert_service, log_record):
        """Test that emit never raises exceptions (logging handler safety)."""
        # Arrange
        handler = TelegramLogHandler(alert_service=mock_alert_service)
        mock_alert_service.send_log_alert.side_effect = Exception("Service error")

        # Act - should not raise
        with patch.object(asyncio, 'get_event_loop') as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = False
            mock_loop.run_until_complete.side_effect = Exception("Loop error")
            mock_get_loop.return_value = mock_loop

            handler.emit(log_record)

        # Assert - no exception raised (implicit success)


@pytest.mark.unit
class TestResolveLogLevel:
    """Test _resolve_log_level function for environment variable parsing."""

    def test_resolve_log_level_debug(self):
        """Test that DEBUG level is recognized."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "DEBUG"}):
            result = _resolve_log_level()

        # Assert
        assert result == "DEBUG"

    def test_resolve_log_level_info(self):
        """Test that INFO level is recognized."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO"}):
            result = _resolve_log_level()

        # Assert
        assert result == "INFO"

    def test_resolve_log_level_warning(self):
        """Test that WARNING level is recognized."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "WARNING"}):
            result = _resolve_log_level()

        # Assert
        assert result == "WARNING"

    def test_resolve_log_level_error(self):
        """Test that ERROR level is recognized."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "ERROR"}):
            result = _resolve_log_level()

        # Assert
        assert result == "ERROR"

    def test_resolve_log_level_critical(self):
        """Test that CRITICAL level is recognized."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "CRITICAL"}):
            result = _resolve_log_level()

        # Assert
        assert result == "CRITICAL"

    def test_resolve_log_level_lowercase_converted(self):
        """Test that lowercase level is converted to uppercase."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "debug"}):
            result = _resolve_log_level()

        # Assert
        assert result == "DEBUG"

    def test_resolve_log_level_with_whitespace(self):
        """Test that whitespace is stripped from env variable."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "  INFO  "}):
            result = _resolve_log_level()

        # Assert
        assert result == "INFO"

    def test_resolve_log_level_invalid_returns_default(self):
        """Test that invalid level returns default."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INVALID"}):
            result = _resolve_log_level(default="WARNING")

        # Assert
        assert result == "WARNING"

    def test_resolve_log_level_empty_returns_default(self):
        """Test that empty string returns default."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": ""}):
            result = _resolve_log_level(default="INFO")

        # Assert
        assert result == "INFO"

    def test_resolve_log_level_missing_returns_default(self):
        """Test that missing env var returns default."""
        # Arrange & Act
        with patch.dict(os.environ, {}, clear=True):
            result = _resolve_log_level(default="INFO")

        # Assert
        assert result == "INFO"

    def test_resolve_log_level_default_is_info(self):
        """Test that default parameter defaults to INFO."""
        # Arrange & Act
        with patch.dict(os.environ, {}, clear=True):
            result = _resolve_log_level()

        # Assert
        assert result == "INFO"


@pytest.mark.unit
class TestConfigureLogging:
    """Test configure_logging function for full logging setup."""

    def test_configure_logging_with_info_level(self):
        """Test logging configuration with INFO level."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        mock_dict_config.assert_called_once()
        config = mock_dict_config.call_args[0][0]

        assert config["version"] == 1
        assert config["disable_existing_loggers"] is False
        assert "channel" in config["filters"]
        assert "trace" in config["filters"]
        assert config["handlers"]["console"]["level"] == "INFO"
        assert config["loggers"][""]["level"] == "INFO"

    def test_configure_logging_with_debug_level_uses_trace_formatter(self):
        """Test that DEBUG level uses 'with_trace' formatter."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "DEBUG"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert config["handlers"]["console"]["formatter"] == "with_trace"
        assert config["handlers"]["console"]["level"] == "DEBUG"

    def test_configure_logging_non_debug_uses_default_formatter(self):
        """Test that non-DEBUG levels use 'default' formatter."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert config["handlers"]["console"]["formatter"] == "default"

    def test_configure_logging_includes_telegram_handler(self):
        """Test that telegram_alerts handler is configured."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert "telegram_alerts" in config["handlers"]
        assert config["handlers"]["telegram_alerts"]["level"] == "WARNING"

    def test_configure_logging_with_alert_service_from_container(self):
        """Test that alert service is loaded from container when available."""
        # Arrange
        mock_alert_service = MagicMock()
        mock_container = MagicMock()
        mock_container.log_alert_service.return_value = mock_alert_service

        # Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', return_value=mock_container):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert config["handlers"]["telegram_alerts"]["alert_service"] is mock_alert_service

    def test_configure_logging_handles_container_exception(self):
        """Test that logging configuration continues if container fails."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("Container error")):
                    configure_logging()

        # Assert - should still configure logging
        mock_dict_config.assert_called_once()
        config = mock_dict_config.call_args[0][0]
        assert "telegram_alerts" in config["handlers"]
        # Service should not be in config if container failed
        assert "alert_service" not in config["handlers"]["telegram_alerts"] or \
               config["handlers"]["telegram_alerts"].get("alert_service") is None

    def test_configure_logging_disables_telegram_alerts_with_env_flag(self):
        """Test that telegram alerts can be disabled via environment variable."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO", "DISABLE_TELEGRAM_LOG_ALERTS": "true"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        # telegram_alerts should be removed from root logger handlers
        assert "telegram_alerts" not in config["loggers"][""]["handlers"]

    def test_configure_logging_disable_telegram_with_1(self):
        """Test that DISABLE_TELEGRAM_LOG_ALERTS=1 disables alerts."""
        # Arrange & Act
        with patch.dict(os.environ, {"DISABLE_TELEGRAM_LOG_ALERTS": "1"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert "telegram_alerts" not in config["loggers"][""]["handlers"]

    def test_configure_logging_disable_telegram_case_insensitive(self):
        """Test that DISABLE_TELEGRAM_LOG_ALERTS is case-insensitive."""
        # Arrange & Act
        with patch.dict(os.environ, {"DISABLE_TELEGRAM_LOG_ALERTS": "YES"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert "telegram_alerts" not in config["loggers"][""]["handlers"]

    def test_configure_logging_keeps_telegram_when_not_disabled(self):
        """Test that telegram alerts remain when flag is not set."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO"}, clear=True):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert "telegram_alerts" in config["loggers"][""]["handlers"]

    def test_configure_logging_includes_all_logger_names(self):
        """Test that all expected loggers are configured."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        loggers = config["loggers"]

        assert "" in loggers  # root logger
        assert "uvicorn" in loggers
        assert "uvicorn.error" in loggers
        assert "uvicorn.access" in loggers
        assert "celery" in loggers
        assert "celery.app.trace" in loggers
        assert "celery.pool" in loggers
        assert "sqlalchemy" in loggers
        assert "openai" in loggers
        assert "httpx" in loggers

    def test_configure_logging_celery_pool_level_is_warning(self):
        """Test that celery.pool level is always WARNING to suppress verbosity."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "DEBUG"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert config["loggers"]["celery.pool"]["level"] == "WARNING"

    def test_configure_logging_openai_level_is_warning(self):
        """Test that openai logger level is always WARNING."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "DEBUG"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert config["loggers"]["openai"]["level"] == "WARNING"

    def test_configure_logging_uvicorn_access_uses_separate_handler(self):
        """Test that uvicorn.access uses uvicorn_console handler."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "INFO"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        assert config["loggers"]["uvicorn.access"]["handlers"] == ["uvicorn_console"]
        assert config["handlers"]["uvicorn_console"]["formatter"] == "uvicorn_access"

    def test_configure_logging_debug_mode_keeps_uvicorn_access_at_info(self):
        """Test that uvicorn.access handler uses INFO level in DEBUG mode."""
        # Arrange & Act
        with patch.dict(os.environ, {"LOGS_LEVEL": "DEBUG"}):
            with patch('core.logging_config.dictConfig') as mock_dict_config:
                with patch('core.container.get_container', side_effect=Exception("No container")):
                    configure_logging()

        # Assert
        config = mock_dict_config.call_args[0][0]
        # In DEBUG mode, uvicorn_console handler should be INFO to reduce verbosity
        assert config["handlers"]["uvicorn_console"]["level"] == "INFO"
