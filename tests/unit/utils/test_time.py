"""Unit tests for time utilities."""

import pytest
from datetime import datetime, timezone, timedelta

from core.utils.time import now_utc, to_utc, iso_utc, now_db_utc


@pytest.mark.unit
class TestTimeUtils:
    """Test time utility functions."""

    def test_now_utc_returns_aware_datetime(self):
        """Test that now_utc returns timezone-aware datetime."""
        # Act
        result = now_utc()

        # Assert
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

    def test_now_utc_is_current_time(self):
        """Test that now_utc returns current time."""
        # Arrange
        before = datetime.now(timezone.utc)

        # Act
        result = now_utc()

        # Assert
        after = datetime.now(timezone.utc)
        assert before <= result <= after

    def test_to_utc_with_naive_datetime(self):
        """Test to_utc treats naive datetime as UTC and marks it."""
        # Arrange
        naive_dt = datetime(2024, 1, 15, 10, 30, 0)

        # Act
        result = to_utc(naive_dt)

        # Assert
        assert result.tzinfo == timezone.utc
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_to_utc_with_aware_datetime_utc(self):
        """Test to_utc with already UTC-aware datetime."""
        # Arrange
        aware_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        # Act
        result = to_utc(aware_dt)

        # Assert
        assert result.tzinfo == timezone.utc
        assert result == aware_dt

    def test_to_utc_converts_other_timezone_to_utc(self):
        """Test to_utc converts non-UTC timezone to UTC."""
        # Arrange - 10:00 EST (UTC-5) = 15:00 UTC
        from datetime import timezone as tz
        est = tz(timedelta(hours=-5))
        aware_dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=est)

        # Act
        result = to_utc(aware_dt)

        # Assert
        assert result.tzinfo == timezone.utc
        assert result.hour == 15  # Converted to UTC

    def test_iso_utc_with_datetime(self):
        """Test iso_utc returns ISO-8601 string for given datetime."""
        # Arrange
        dt = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)

        # Act
        result = iso_utc(dt)

        # Assert
        assert isinstance(result, str)
        assert "2024-01-15" in result
        assert "10:30:45" in result
        assert "+00:00" in result or "Z" in result

    def test_iso_utc_without_datetime_uses_current(self):
        """Test iso_utc without argument uses current time."""
        # Act
        result = iso_utc()

        # Assert
        assert isinstance(result, str)
        # Should be valid ISO format
        parsed = datetime.fromisoformat(result.replace('Z', '+00:00'))
        assert parsed.tzinfo is not None

    def test_iso_utc_with_none_uses_current(self):
        """Test iso_utc with None argument uses current time."""
        # Act
        result = iso_utc(None)

        # Assert
        assert isinstance(result, str)
        parsed = datetime.fromisoformat(result.replace('Z', '+00:00'))
        assert parsed.tzinfo is not None

    def test_now_db_utc_returns_naive_datetime(self):
        """Test that now_db_utc returns naive datetime for database compatibility."""
        # Act
        result = now_db_utc()

        # Assert
        assert isinstance(result, datetime)
        assert result.tzinfo is None  # Naive datetime

    def test_now_db_utc_is_current_utc_time(self):
        """Test that now_db_utc returns current UTC time without timezone info."""
        # Arrange
        before = datetime.now(timezone.utc).replace(tzinfo=None)

        # Act
        result = now_db_utc()

        # Assert
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert before <= result <= after

    def test_now_db_utc_matches_now_utc_values(self):
        """Test that now_db_utc has same time values as now_utc, just without tzinfo."""
        # Act
        aware = now_utc()
        naive = now_db_utc()

        # Assert - should be within 1 second of each other
        assert abs((aware.replace(tzinfo=None) - naive).total_seconds()) < 1
