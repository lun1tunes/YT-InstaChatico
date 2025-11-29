from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List

from sqlalchemy.ext.asyncio import AsyncSession

from .generate_stats_report import StatsPeriod
from ..interfaces.repositories import (
    IModerationStatsRepository,
    IModerationStatsReportRepository,
)

logger = logging.getLogger(__name__)


class ModerationStatsError(Exception):
    """Domain error for moderation stats generation."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ModerationMonthRange:
    label: str
    start: datetime
    end: datetime
    since: int
    until: int
    is_current: bool


class GenerateModerationStatsUseCase:
    """Generate moderation stats grouped per month for the requested period."""

    _PERIOD_TO_MONTHS = {
        StatsPeriod.LAST_WEEK: 0,
        StatsPeriod.LAST_MONTH: 1,
        StatsPeriod.LAST_3_MONTHS: 3,
        StatsPeriod.LAST_6_MONTHS: 6,
    }

    def __init__(
        self,
        session: AsyncSession,
        moderation_stats_repository_factory: Callable[..., IModerationStatsRepository],
        moderation_stats_report_repository_factory: Callable[..., IModerationStatsReportRepository],
    ):
        self.session = session
        self.repo: IModerationStatsRepository = moderation_stats_repository_factory(session=session)
        self.cache_repo: IModerationStatsReportRepository = moderation_stats_report_repository_factory(session=session)

    async def execute(self, period: StatsPeriod) -> dict[str, Any]:
        month_ranges = self._build_month_ranges(period)
        logger.info(
            "Generating moderation stats | period=%s | months=%s",
            period.value,
            [m.label for m in month_ranges],
        )

        months_payload: List[dict[str, Any]] = []
        current_label = month_ranges[-1].label

        for month_range in month_ranges:
            range_start = month_range.start.replace(tzinfo=None)
            range_end = month_range.end.replace(tzinfo=None)

            if not month_range.is_current:
                cached = await self.cache_repo.get_by_range(range_start, range_end)
                if cached:
                    months_payload.append(cached.payload)
                    continue

            metrics = await self.repo.gather_metrics(range_start, range_end)
            payload = {
                "month": month_range.label,
                "range": {"since": month_range.since, "until": month_range.until},
                **metrics,
            }

            await self.cache_repo.save_month_report(
                period_label=month_range.label,
                range_start=range_start,
                range_end=range_end,
                payload=payload,
            )
            months_payload.append(payload)

        return {
            "period": period.value,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "months": months_payload,
        }

    def _build_month_ranges(self, period: StatsPeriod) -> List[ModerationMonthRange]:
        previous_months = self._PERIOD_TO_MONTHS.get(period)
        if previous_months is None:
            raise ModerationStatsError("Unsupported period", status_code=400)

        now = datetime.now(timezone.utc)
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        starts = [current_month_start]

        rolling_start = current_month_start
        for _ in range(previous_months):
            rolling_start = self._shift_month(rolling_start, -1)
            starts.append(rolling_start)

        month_ranges: List[ModerationMonthRange] = []
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        for start in sorted(starts):
            is_current = start == current_month_start
            end = tomorrow if is_current else self._shift_month(start, 1)
            month_ranges.append(
                ModerationMonthRange(
                    label=f"{start.year}-{start.month:02d}",
                    start=start,
                    end=end,
                    since=int(start.timestamp()),
                    until=int(end.timestamp()),
                    is_current=is_current,
                )
            )

        return month_ranges

    def _shift_month(self, dt: datetime, delta_months: int) -> datetime:
        year = dt.year + (dt.month - 1 + delta_months) // 12
        month = (dt.month - 1 + delta_months) % 12 + 1
        return datetime(year, month, 1, tzinfo=dt.tzinfo)
