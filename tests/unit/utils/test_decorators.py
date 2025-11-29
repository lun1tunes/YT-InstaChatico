"""Unit tests for decorator utilities."""

import pytest
import logging
from unittest.mock import patch, MagicMock

from core.utils.decorators import handle_task_errors, log_execution, validate_not_none


@pytest.mark.unit
class TestHandleTaskErrors:
    """Test handle_task_errors decorator."""

    async def test_handle_task_errors_success(self):
        """Test decorator passes through successful function result."""
        # Arrange
        @handle_task_errors()
        async def successful_function():
            return {"status": "success", "data": "test"}

        # Act
        result = await successful_function()

        # Assert
        assert result == {"status": "success", "data": "test"}

    async def test_handle_task_errors_catches_exception(self):
        """Test decorator catches and logs exceptions."""
        # Arrange
        @handle_task_errors()
        async def failing_function():
            raise ValueError("Test error")

        # Act
        with patch('core.utils.decorators.logger') as mock_logger:
            result = await failing_function()

        # Assert
        assert result["status"] == "error"
        assert "Test error" in result["reason"]
        mock_logger.exception.assert_called_once()

    async def test_handle_task_errors_custom_status(self):
        """Test decorator with custom error status."""
        # Arrange
        @handle_task_errors(error_status="failed")
        async def failing_function():
            raise RuntimeError("Custom error")

        # Act
        result = await failing_function()

        # Assert
        assert result["status"] == "failed"
        assert "Custom error" in result["reason"]

    async def test_handle_task_errors_preserves_function_name(self):
        """Test decorator preserves original function name."""
        # Arrange
        @handle_task_errors()
        async def my_custom_function():
            return "ok"

        # Assert
        assert my_custom_function.__name__ == "my_custom_function"

    async def test_handle_task_errors_with_different_exceptions(self):
        """Test decorator handles different exception types."""
        # Arrange
        @handle_task_errors()
        async def type_error_function():
            raise TypeError("Type mismatch")

        @handle_task_errors()
        async def key_error_function():
            raise KeyError("Missing key")

        # Act
        result1 = await type_error_function()
        result2 = await key_error_function()

        # Assert
        assert "Type mismatch" in result1["reason"]
        assert "Missing key" in result2["reason"]


@pytest.mark.unit
class TestLogExecution:
    """Test log_execution decorator."""

    async def test_log_execution_with_args_logged(self):
        """Test decorator logs function execution with arguments."""
        # Arrange
        @log_execution(log_args=True)
        async def test_function(arg1, arg2, kwarg1=None):
            return "result"

        # Act
        with patch('core.utils.decorators.logger') as mock_logger:
            result = await test_function("value1", "value2", kwarg1="kwvalue")

        # Assert
        assert result == "result"
        assert mock_logger.debug.call_count == 2  # Start and completion

        # Check start log
        start_call = mock_logger.debug.call_args_list[0][0][0]
        assert "Executing test_function" in start_call
        assert "args=" in start_call

        # Check completion log
        completion_call = mock_logger.debug.call_args_list[1][0][0]
        assert "Completed test_function" in completion_call

    async def test_log_execution_without_args_logged(self):
        """Test decorator logs execution without showing arguments."""
        # Arrange
        @log_execution(log_args=False)
        async def test_function(secret_arg):
            return "result"

        # Act
        with patch('core.utils.decorators.logger') as mock_logger:
            result = await test_function("sensitive_data")

        # Assert
        assert result == "result"

        # Check start log doesn't contain args
        start_call = mock_logger.debug.call_args_list[0][0][0]
        assert "Executing test_function" in start_call
        assert "args=" not in start_call
        assert "sensitive_data" not in start_call

    async def test_log_execution_preserves_function_name(self):
        """Test decorator preserves original function name."""
        # Arrange
        @log_execution()
        async def my_logged_function():
            return "ok"

        # Assert
        assert my_logged_function.__name__ == "my_logged_function"

    async def test_log_execution_returns_function_result(self):
        """Test decorator returns the actual function result."""
        # Arrange
        @log_execution()
        async def calculation_function(x, y):
            return x + y

        # Act
        result = await calculation_function(5, 3)

        # Assert
        assert result == 8

    async def test_log_execution_propagates_exception(self):
        """Decorator should not swallow exceptions from the wrapped function."""
        # Arrange
        @log_execution()
        async def failing_function():
            raise RuntimeError("boom")

        # Act & Assert
        with patch('core.utils.decorators.logger') as mock_logger:
            with pytest.raises(RuntimeError, match="boom"):
                await failing_function()

        # Only the start log should be emitted; completion log is skipped
        assert mock_logger.debug.call_count == 1
        assert "Executing failing_function" in mock_logger.debug.call_args[0][0]


@pytest.mark.unit
class TestValidateNotNone:
    """Test validate_not_none decorator."""

    async def test_validate_not_none_success(self):
        """Test decorator passes when all fields are not None."""
        # Arrange
        @validate_not_none('param1', 'param2')
        async def test_function(param1, param2):
            return f"{param1}-{param2}"

        # Act
        result = await test_function("value1", "value2")

        # Assert
        assert result == "value1-value2"

    async def test_validate_not_none_raises_on_none_positional(self):
        """Test decorator raises ValueError when positional argument is None."""
        # Arrange
        @validate_not_none('param1')
        async def test_function(param1):
            return param1

        # Act & Assert
        with pytest.raises(ValueError, match="param1 cannot be None"):
            await test_function(None)

    async def test_validate_not_none_raises_on_none_keyword(self):
        """Test decorator raises ValueError when keyword argument is None."""
        # Arrange
        @validate_not_none('param2')
        async def test_function(param1, param2=None):
            return f"{param1}-{param2}"

        # Act & Assert
        with pytest.raises(ValueError, match="param2 cannot be None"):
            await test_function("value1", param2=None)

    async def test_validate_not_none_multiple_fields(self):
        """Test decorator validates multiple fields."""
        # Arrange
        @validate_not_none('field1', 'field2', 'field3')
        async def test_function(field1, field2, field3):
            return "ok"

        # Act - All valid
        result = await test_function("a", "b", "c")
        assert result == "ok"

        # Act & Assert - field2 is None
        with pytest.raises(ValueError, match="field2 cannot be None"):
            await test_function("a", None, "c")

    async def test_validate_not_none_preserves_function_name(self):
        """Test decorator preserves original function name."""
        # Arrange
        @validate_not_none('param')
        async def my_validated_function(param):
            return "ok"

        # Assert
        assert my_validated_function.__name__ == "my_validated_function"

    async def test_validate_not_none_with_defaults(self):
        """Test decorator works with default parameter values."""
        # Arrange
        @validate_not_none('required_param')
        async def test_function(required_param, optional_param="default"):
            return f"{required_param}-{optional_param}"

        # Act
        result = await test_function("value")

        # Assert
        assert result == "value-default"

    async def test_validate_not_none_ignores_non_specified_fields(self):
        """Test decorator only validates specified fields."""
        # Arrange
        @validate_not_none('field1')
        async def test_function(field1, field2):
            return f"{field1}-{field2}"

        # Act - field2 can be None since it's not validated
        result = await test_function("value", None)

        # Assert
        assert result == "value-None"

    async def test_validate_not_none_with_kwargs(self):
        """Test decorator works with **kwargs."""
        # Arrange
        @validate_not_none('required')
        async def test_function(required, **kwargs):
            return f"{required}-{kwargs.get('extra', 'no-extra')}"

        # Act
        result = await test_function("value", extra="data")

        # Assert
        assert result == "value-data"

    async def test_validate_not_none_missing_field_ignored(self):
        """Fields not present in signature should be ignored gracefully."""
        @validate_not_none('nonexistent')
        async def test_function(existing):
            return existing

        result = await test_function("value")
        assert result == "value"

    async def test_validate_not_none_default_none_triggers_error(self):
        """Default None values should still trigger validation."""
        @validate_not_none('param')
        async def test_function(param=None):
            return param

        with pytest.raises(ValueError, match="param cannot be None"):
            await test_function()
