"""Shared retry policy constants for tasks and use cases."""

DEFAULT_RETRY_SCHEDULE: tuple[int, ...] = (15, 60, 300, 900, 3600)
DEFAULT_MAX_RETRIES: int = len(DEFAULT_RETRY_SCHEDULE)

