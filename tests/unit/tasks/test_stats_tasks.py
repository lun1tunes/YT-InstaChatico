import pytest

from core.tasks.stats_tasks import record_follower_snapshot_task_async
from core.use_cases.record_follower_snapshot import FollowersSnapshotError


class DummySession:
    pass


class DummySessionContext:
    def __init__(self):
        self.session = DummySession()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class StubUseCase:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = 0

    async def execute(self):
        self.calls += 1
        if self.should_fail:
            raise FollowersSnapshotError("boom")
        return {"snapshot_date": "2025-11-17", "followers_count": 200}


class StubContainer:
    def __init__(self, use_case):
        self.use_case = use_case
        self.sessions = []

    def record_follower_snapshot_use_case(self, session):
        self.sessions.append(session)
        return self.use_case


@pytest.mark.unit
class TestRecordFollowerSnapshotTask:
    @pytest.mark.asyncio
    async def test_task_success(self, monkeypatch):
        use_case = StubUseCase()
        container = StubContainer(use_case)

        monkeypatch.setattr("core.tasks.stats_tasks.get_container", lambda: container)
        monkeypatch.setattr("core.tasks.stats_tasks.get_db_session", lambda: DummySessionContext())

        result = await record_follower_snapshot_task_async()

        assert result["status"] == "ok"
        assert result["followers_count"] == 200
        assert use_case.calls == 1
        assert len(container.sessions) == 1

    @pytest.mark.asyncio
    async def test_task_failure(self, monkeypatch):
        use_case = StubUseCase(should_fail=True)
        container = StubContainer(use_case)

        monkeypatch.setattr("core.tasks.stats_tasks.get_container", lambda: container)
        monkeypatch.setattr("core.tasks.stats_tasks.get_db_session", lambda: DummySessionContext())

        result = await record_follower_snapshot_task_async()

        assert result["status"] == "error"
        assert "reason" in result
        assert use_case.calls == 1
