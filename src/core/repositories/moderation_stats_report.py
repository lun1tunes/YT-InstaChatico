from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.moderation_stats_report import ModerationStatsReport


class ModerationStatsReportRepository(BaseRepository[ModerationStatsReport]):
    def __init__(self, session: AsyncSession):
        super().__init__(ModerationStatsReport, session)

    async def get_by_range(self, range_start, range_end) -> ModerationStatsReport | None:
        stmt = select(ModerationStatsReport).where(
            ModerationStatsReport.range_start == range_start,
            ModerationStatsReport.range_end == range_end,
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
    ) -> ModerationStatsReport:
        report = await self.get_by_range(range_start, range_end)
        if report:
            report.period_label = period_label
            report.payload = payload
        else:
            report = ModerationStatsReport(
                period_label=period_label,
                range_start=range_start,
                range_end=range_end,
                payload=payload,
            )
            self.session.add(report)

        await self.session.flush()
        return report
