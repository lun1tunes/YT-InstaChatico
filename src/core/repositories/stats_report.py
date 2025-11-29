from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.stats_report import StatsReport


class StatsReportRepository(BaseRepository[StatsReport]):
    def __init__(self, session: AsyncSession):
        super().__init__(StatsReport, session)

    async def get_by_range(self, range_start, range_end) -> StatsReport | None:
        stmt = select(StatsReport).where(
            StatsReport.range_start == range_start,
            StatsReport.range_end == range_end,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_month_report(
        self,
        *,
        period_label: str,
        range_start,
        range_end,
        payload: dict,
    ) -> StatsReport:
        report = await self.get_by_range(range_start, range_end)
        if report:
            report.period_label = period_label
            report.payload = payload
        else:
            report = StatsReport(
                period_label=period_label,
                range_start=range_start,
                range_end=range_end,
                payload=payload,
            )
            self.session.add(report)

        await self.session.flush()
        return report
