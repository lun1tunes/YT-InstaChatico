from __future__ import annotations

from datetime import date

import pytest

from core.use_cases.record_follower_snapshot import (
    RecordFollowerSnapshotUseCase,
    FollowersSnapshotError,
)


class FakeFollowersRepo:
    def __init__(self):
        self.saved = []

    async def upsert_snapshot(self, **kwargs):
        self.saved.append(kwargs)
        return type(
            "Record",
            (),
            {
                "followers_count": kwargs["followers_count"],
                "follows_count": kwargs.get("follows_count"),
                "media_count": kwargs.get("media_count"),
            },
        )()


class FakeInstagramService:
    def __init__(self, success=True):
        self.success = success

    async def get_account_profile(self):
        if not self.success:
            return {"success": False, "error": "fail"}
        return {
            "success": True,
            "data": {
                "username": "test",
                "followers_count": 123,
                "follows_count": 50,
                "media_count": 7,
            },
        }


@pytest.mark.asyncio
async def test_record_follower_snapshot_success(db_session):
    repo = FakeFollowersRepo()
    service = FakeInstagramService()
    use_case = RecordFollowerSnapshotUseCase(
        session=db_session,
        instagram_service=service,
        followers_dynamic_repository_factory=lambda session: repo,
    )

    result = await use_case.execute(snapshot_date=date(2025, 11, 17))

    assert result["followers_count"] == 123
    assert repo.saved[0]["snapshot_date"] == date(2025, 11, 17)


@pytest.mark.asyncio
async def test_record_follower_snapshot_failure(db_session):
    repo = FakeFollowersRepo()
    service = FakeInstagramService(success=False)
    use_case = RecordFollowerSnapshotUseCase(
        session=db_session,
        instagram_service=service,
        followers_dynamic_repository_factory=lambda session: repo,
    )

    with pytest.raises(FollowersSnapshotError):
        await use_case.execute(snapshot_date=date(2025, 11, 17))
