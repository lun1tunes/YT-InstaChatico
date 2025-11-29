from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces.repositories import IFollowersDynamicRepository
from ..interfaces.services import IInstagramService

logger = logging.getLogger(__name__)


class FollowersSnapshotError(Exception):
    """Raised when recording followers snapshot fails."""


class RecordFollowerSnapshotUseCase:
    """Persist daily Instagram followers metrics."""

    def __init__(
        self,
        session: AsyncSession,
        instagram_service: IInstagramService,
        followers_dynamic_repository_factory: Callable[..., IFollowersDynamicRepository],
    ):
        self.session = session
        self.instagram_service = instagram_service
        self.repo: IFollowersDynamicRepository = followers_dynamic_repository_factory(session=session)

    async def execute(self, snapshot_date: date | None = None) -> dict:
        target_date = snapshot_date or datetime.now(timezone.utc).date()

        payload = await self._fetch_account_payload()
        followers_count = self._safe_int(payload.get("followers_count"), default=0)
        follows_count = self._safe_int(payload.get("follows_count"))
        media_count = self._safe_int(payload.get("media_count"))
        username = payload.get("username")

        try:
            record = await self.repo.upsert_snapshot(
                snapshot_date=target_date,
                username=username,
                followers_count=followers_count,
                follows_count=follows_count,
                media_count=media_count,
                raw_payload=payload,
            )
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            logger.exception("Failed to store followers snapshot")
            raise FollowersSnapshotError("Failed to store followers snapshot") from exc

        logger.info(
            "Recorded Instagram followers snapshot | date=%s | followers=%s",
            target_date.isoformat(),
            followers_count,
        )
        return {
            "snapshot_date": target_date.isoformat(),
            "followers_count": record.followers_count,
            "follows_count": record.follows_count,
            "media_count": record.media_count,
        }

    async def _fetch_account_payload(self) -> dict[str, Any]:
        try:
            result = await self.instagram_service.get_account_profile()
        except Exception as exc:
            logger.exception("Failed to fetch Instagram account profile")
            raise FollowersSnapshotError("Failed to fetch Instagram account profile") from exc

        if not result.get("success"):
            logger.error("Instagram account profile request failed | error=%s", result.get("error"))
            raise FollowersSnapshotError("Instagram account profile request failed")

        payload = result.get("data") or {}
        if not isinstance(payload, dict):
            payload = dict(payload)
        return payload

    @staticmethod
    def _safe_int(value: Any, default: int | None = None) -> int | None:
        if value in (None, ""):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
