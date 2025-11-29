import pytest
from datetime import datetime

from core.repositories.stats_report import StatsReportRepository
from core.models.stats_report import StatsReport


def _month_range(year: int, month: int):
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


@pytest.mark.unit
@pytest.mark.repository
class TestStatsReportRepository:
    async def test_get_by_range_returns_record(self, db_session):
        repo = StatsReportRepository(db_session)
        start, end = _month_range(2025, 8)
        record = StatsReport(
            period_label="2025-08",
            range_start=start,
            range_end=end,
            payload={"month": "aug"},
        )
        db_session.add(record)
        await db_session.flush()

        result = await repo.get_by_range(start, end)

        assert result is not None
        assert result.payload["month"] == "aug"

    async def test_save_month_report_creates_new_record(self, db_session):
        repo = StatsReportRepository(db_session)
        start, end = _month_range(2025, 9)

        report = await repo.save_month_report(
            period_label="2025-09",
            range_start=start,
            range_end=end,
            payload={"month": "sep", "value": 42},
        )

        assert report.id is not None
        assert report.payload["value"] == 42

        fetched = await repo.get_by_range(start, end)
        assert fetched is not None
        assert fetched.id == report.id

    async def test_save_month_report_updates_existing(self, db_session):
        repo = StatsReportRepository(db_session)
        start, end = _month_range(2025, 10)
        existing = StatsReport(
            period_label="old",
            range_start=start,
            range_end=end,
            payload={"month": "old"},
        )
        db_session.add(existing)
        await db_session.flush()

        updated = await repo.save_month_report(
            period_label="2025-10",
            range_start=start,
            range_end=end,
            payload={"month": "oct", "value": 100},
        )

        assert updated.id == existing.id
        assert updated.payload["value"] == 100
        assert updated.period_label == "2025-10"
