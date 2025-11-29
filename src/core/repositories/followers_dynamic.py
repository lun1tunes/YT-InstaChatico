"""Repository for followers dynamics snapshots."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.followers_dynamic import FollowersDynamic


class FollowersDynamicRepository(BaseRepository[FollowersDynamic]):
    """Manage persistence of daily followers snapshots."""

    def __init__(self, session: AsyncSession):
        super().__init__(FollowersDynamic, session)

    async def get_by_snapshot_date(self, snapshot_date: date) -> FollowersDynamic | None:
        stmt = select(FollowersDynamic).where(FollowersDynamic.snapshot_date == snapshot_date)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_snapshot(
        self,
        *,
        snapshot_date: date,
        username: str | None,
        followers_count: int,
        follows_count: int | None,
        media_count: int | None,
        raw_payload: dict,
    ) -> FollowersDynamic:
        record = await self.get_by_snapshot_date(snapshot_date)
        if record:
            record.username = username
            record.followers_count = followers_count
            record.follows_count = follows_count
            record.media_count = media_count
            record.raw_payload = raw_payload
        else:
            record = FollowersDynamic(
                snapshot_date=snapshot_date,
                username=username,
                followers_count=followers_count,
                follows_count=follows_count,
                media_count=media_count,
                raw_payload=raw_payload,
            )
            self.session.add(record)

        await self.session.flush()
        return record
