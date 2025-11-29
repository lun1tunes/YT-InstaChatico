from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.config import settings
from core.use_cases import generate_stats_report as stats_module
from core.use_cases.generate_stats_report import (
    GenerateStatsReportUseCase,
    StatsPeriod,
    StatsReportError,
)


class DummyReport:
    def __init__(self, payload):
        self.payload = payload


class FakeStatsReportRepository:
    def __init__(self, cached=None):
        self.cached = cached or {}
        self.saved = []
        self.range_queries = []

    async def get_by_range(self, range_start, range_end):
        self.range_queries.append((range_start, range_end))
        return self.cached.get((range_start, range_end))

    async def save_month_report(
        self,
        *,
        period_label: str,
        range_start,
        range_end,
        payload: dict,
    ):
        report = DummyReport(payload)
        self.cached[(range_start, range_end)] = report
        self.saved.append((period_label, range_start, range_end))
        return report


class FakeInstagramService:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    async def get_insights(self, account_id: str, params: dict):
        self.calls.append({"account_id": account_id, **params})
        if not self.success:
            return {"success": False, "error": "boom"}
        return {
            "success": True,
            "data": {
                "metric": params["metric"],
                "since": params["since"],
                "until": params["until"],
            },
        }


def _month_key(year: int, month: int):
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def _freeze_now(monkeypatch, target):
    fixed_now = datetime(2025, 11, 16, 12, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(target, "datetime", FrozenDateTime)
    return fixed_now


@pytest.mark.asyncio
async def test_generate_stats_report_reuses_cached_months(monkeypatch, db_session):
    _freeze_now(monkeypatch, stats_module)
    monkeypatch.setattr(settings.instagram, "base_account_id", "17841476998475313")

    cached = {}
    for label, (start, end) in {
        "2025-08": _month_key(2025, 8),
        "2025-09": _month_key(2025, 9),
        "2025-10": _month_key(2025, 10),
    }.items():
        cached[(start, end)] = DummyReport(
            payload={
                "month": label,
                "range": {"since": int(start.timestamp()), "until": int(end.timestamp())},
                "cached": True,
                "insights": {
                    "engagement": {"metric": "views,likes"},
                    "replies": {},
                    "profile_links": {},
                    "follow_type": {},
                },
            }
        )

    repo = FakeStatsReportRepository(cached=cached)
    service = FakeInstagramService()

    use_case = GenerateStatsReportUseCase(
        session=db_session,
        instagram_service=service,
        stats_report_repository_factory=lambda session: repo,
    )

    result = await use_case.execute(StatsPeriod.LAST_3_MONTHS)

    assert len(result["months"]) == 4
    # Cached months reused
    assert result["months"][0]["cached"] is True
    assert result["months"][1]["cached"] is True
    assert result["months"][2]["cached"] is True
    # Current month fetched from Instagram
    current_month = result["months"][3]
    engagement_payload = current_month["insights"]["engagement"]
    metric_name = engagement_payload.get("metric") or engagement_payload.get("data", [{}])[0].get("metric")
    assert metric_name.split(",")[0] == "views"
    assert len(service.calls) == 4  # four metrics for current month
    assert len(repo.saved) == 1  # only current month stored
    # Ensure cached ranges were looked up
    assert len(repo.range_queries) == 3


@pytest.mark.asyncio
async def test_generate_stats_report_handles_missing_account(monkeypatch, db_session):
    _freeze_now(monkeypatch, stats_module)
    monkeypatch.setattr(settings.instagram, "base_account_id", "")

    repo = FakeStatsReportRepository()
    service = FakeInstagramService()

    use_case = GenerateStatsReportUseCase(
        session=db_session,
        instagram_service=service,
        stats_report_repository_factory=lambda session: repo,
    )

    with pytest.raises(StatsReportError):
        await use_case.execute(StatsPeriod.LAST_MONTH)


@pytest.mark.asyncio
async def test_generate_stats_report_raises_on_failed_insights(monkeypatch, db_session):
    _freeze_now(monkeypatch, stats_module)
    monkeypatch.setattr(settings.instagram, "base_account_id", "17841476998475313")

    repo = FakeStatsReportRepository()
    service = FakeInstagramService(success=False)

    use_case = GenerateStatsReportUseCase(
        session=db_session,
        instagram_service=service,
        stats_report_repository_factory=lambda session: repo,
    )

    with pytest.raises(StatsReportError):
        await use_case.execute(StatsPeriod.LAST_WEEK)
