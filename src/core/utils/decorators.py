"""Common decorators for error handling and logging (DRY principle)."""

import logging
from functools import wraps
from typing import Callable, Any, Dict

logger = logging.getLogger(__name__)


def handle_task_errors(error_status: str = "error"):
    """
    Decorator for consistent error handling in tasks.

    Eliminates duplicate try-except blocks (DRY principle).

    Args:
        error_status: Status to return on error
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Dict[str, Any]:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                if getattr(exc, "should_reraise", False):
                    raise
                logger.exception(f"Error in {func.__name__}: {exc}")
                return {"status": error_status, "reason": str(exc)}

        return wrapper

    return decorator


def log_execution(log_args: bool = True):
    """
    Decorator for logging function execution.

    Args:
        log_args: Whether to log function arguments
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            func_name = func.__name__
            if log_args:
                logger.debug(f"Executing {func_name} with args={args}, kwargs={kwargs}")
            else:
                logger.debug(f"Executing {func_name}")

            result = await func(*args, **kwargs)
            logger.debug(f"Completed {func_name}")
            return result

        return wrapper

    return decorator


def validate_not_none(*field_names: str):
    """
    Decorator for validating that specified fields are not None.

    Eliminates repetitive validation code (DRY principle).

    Usage:
        @validate_not_none('comment', 'classification')
        async def process(comment, classification):
            # No need for if not comment checks
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Get function arguments
            import inspect

            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Validate specified fields
            for field_name in field_names:
                if field_name in bound.arguments and bound.arguments[field_name] is None:
                    raise ValueError(f"{field_name} cannot be None")

            return await func(*args, **kwargs)

        return wrapper

    return decorator
