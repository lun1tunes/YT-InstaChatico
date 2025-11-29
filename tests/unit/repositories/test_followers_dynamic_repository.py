from datetime import date

import pytest

from core.models.followers_dynamic import FollowersDynamic
from core.repositories.followers_dynamic import FollowersDynamicRepository


@pytest.mark.unit
@pytest.mark.repository
class TestFollowersDynamicRepository:
    async def test_upsert_snapshot_creates_record(self, db_session):
        repo = FollowersDynamicRepository(db_session)
        snapshot_date = date(2025, 11, 16)

        record = await repo.upsert_snapshot(
            snapshot_date=snapshot_date,
            username="test",
            followers_count=150,
            follows_count=10,
            media_count=5,
            raw_payload={"followers_count": 150},
        )

        assert record.id is not None
        assert record.followers_count == 150
        assert record.snapshot_date == snapshot_date

    async def test_upsert_snapshot_updates_existing(self, db_session):
        repo = FollowersDynamicRepository(db_session)
        snapshot_date = date(2025, 11, 17)
        existing = FollowersDynamic(
            snapshot_date=snapshot_date,
            username="old",
            followers_count=100,
            follows_count=9,
            media_count=4,
            raw_payload={"followers_count": 100},
        )
        db_session.add(existing)
        await db_session.flush()

        updated = await repo.upsert_snapshot(
            snapshot_date=snapshot_date,
            username="new",
            followers_count=200,
            follows_count=20,
            media_count=10,
            raw_payload={"followers_count": 200},
        )

        assert updated.id == existing.id
        assert updated.followers_count == 200
        assert updated.username == "new"
