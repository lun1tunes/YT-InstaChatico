from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..interfaces.repositories import IStatsReportRepository
from ..interfaces.services import IInstagramService
from ..interfaces.services import IInstagramService

logger = logging.getLogger(__name__)


class StatsReportError(Exception):
    """Domain error for stats report generation."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class StatsPeriod(str, Enum):
    LAST_WEEK = "last_week"
    LAST_MONTH = "last_month"
    LAST_3_MONTHS = "last_3_months"
    LAST_6_MONTHS = "last_6_months"


@dataclass
class MonthRange:
    label: str
    start: datetime
    end: datetime
    since: int
    until: int
    is_current: bool


class GenerateStatsReportUseCase:
    """Generate Instagram insights stats report for a configurable period."""

    _PERIOD_TO_MONTHS = {
        StatsPeriod.LAST_WEEK: 0,
        StatsPeriod.LAST_MONTH: 1,
        StatsPeriod.LAST_3_MONTHS: 3,
        StatsPeriod.LAST_6_MONTHS: 6,
    }

    def __init__(
        self,
        session: AsyncSession,
        instagram_service: IInstagramService,
        stats_report_repository_factory: Callable[..., IStatsReportRepository],
    ):
        self.session = session
        self.instagram_service = instagram_service
        self.stats_repo: IStatsReportRepository = stats_report_repository_factory(session=session)

    async def execute(self, period: StatsPeriod) -> Dict[str, Any]:
        account_id = settings.instagram.base_account_id
        if not account_id:
            raise StatsReportError("Instagram base account ID is not configured", status_code=503)

        month_ranges = self._build_month_ranges(period)
        logger.info(
            "Generating stats report | period=%s | months=%s",
            period.value,
            [m.label for m in month_ranges],
        )

        months_payload: List[Dict[str, Any]] = []
        for month_range in month_ranges:
            month_payload = await self._resolve_month_payload(account_id, month_range)
            months_payload.append(month_payload)

        consolidated = {
            "period": period.value,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "months": months_payload,
        }

        await self.session.commit()
        return consolidated

    def _build_month_ranges(self, period: StatsPeriod) -> List[MonthRange]:
        previous_months = self._PERIOD_TO_MONTHS.get(period)
        if previous_months is None:
            raise StatsReportError("Unsupported period", status_code=400)

        now = datetime.now(timezone.utc)
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        starts = [current_month_start]

        rolling_start = current_month_start
        for _ in range(previous_months):
            rolling_start = self._shift_month(rolling_start, -1)
            starts.append(rolling_start)

        month_ranges: List[MonthRange] = []
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        for start in sorted(starts):
            is_current = start == current_month_start
            end = tomorrow if is_current else self._shift_month(start, 1)
            month_label = f"{start.year}-{start.month:02d}"
            month_ranges.append(
                MonthRange(
                    label=month_label,
                    start=start,
                    end=end,
                    since=int(start.timestamp()),
                    until=int(end.timestamp()),
                    is_current=is_current,
                )
            )

        return month_ranges

    async def _resolve_month_payload(self, account_id: str, month_range: MonthRange) -> Dict[str, Any]:
        range_start = month_range.start.replace(tzinfo=None)
        range_end = month_range.end.replace(tzinfo=None)

        if not month_range.is_current:
            cached = await self.stats_repo.get_by_range(range_start, range_end)
            if cached:
                logger.debug(
                    "Reusing cached stats report | month=%s | range=(%s,%s)",
                    month_range.label,
                    range_start,
                    range_end,
                )
                return cached.payload

        payload = await self._fetch_month_insights(account_id, month_range)
        await self.stats_repo.save_month_report(
            period_label=month_range.label,
            range_start=range_start,
            range_end=range_end,
            payload=payload,
        )
        return payload

    async def _fetch_month_insights(self, account_id: str, month_range: MonthRange) -> Dict[str, Any]:
        timelines = {
            "since": month_range.since,
            "until": month_range.until,
        }

        general_metrics = await self._call_insights(
            account_id,
            {
                "metric": "views,likes,shares,comments,reach,saves,total_interactions",
                "period": "day",
                "breakdown": "media_product_type",
                "metric_type": "total_value",
                **timelines,
            },
        )

        replies_metrics = await self._call_insights(
            account_id,
            {
                "metric": "replies,accounts_engaged",
                "period": "day",
                "metric_type": "total_value",
                **timelines,
            },
        )

        profile_links_metrics = await self._call_insights(
            account_id,
            {
                "metric": "profile_links_taps",
                "period": "day",
                "breakdown": "contact_button_type",
                "metric_type": "total_value",
                **timelines,
            },
        )

        follow_type_metrics = await self._call_insights(
            account_id,
            {
                "metric": "views,reach,follows_and_unfollows",
                "period": "day",
                "breakdown": "follow_type",
                "metric_type": "total_value",
                **timelines,
            },
        )

        return {
            "month": month_range.label,
            "range": {"since": month_range.since, "until": month_range.until},
            "insights": {
                "engagement": general_metrics,
                "replies": replies_metrics,
                "profile_links": profile_links_metrics,
                "follow_type": follow_type_metrics,
            },
        }

    async def _call_insights(self, account_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.instagram_service.get_insights(account_id, params)
        if not result.get("success"):
            message = result.get("error") or "Instagram insights call failed"
            logger.error("Instagram insights error | params=%s | error=%s", params, message)
            raise StatsReportError("Failed to fetch Instagram insights", status_code=502)
        return result.get("data", {})

    def _shift_month(self, dt: datetime, delta_months: int) -> datetime:
        """Return datetime at first day of dt shifted by delta months."""
        year = dt.year + (dt.month - 1 + delta_months) // 12
        month = (dt.month - 1 + delta_months) % 12 + 1
        first_day = datetime(year, month, 1, tzinfo=dt.tzinfo)
        return first_day
