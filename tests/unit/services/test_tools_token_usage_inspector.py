import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.repositories.instrument_token_usage import InstrumentTokenUsageRepository
from core.services.tools_token_usage_inspector import ToolsTokenUsageInspector
from core.models.instrument_token_usage import InstrumentTokenUsage


def _session_factory_provider(db_session):
    return async_sessionmaker(bind=db_session.bind, expire_on_commit=False)


@pytest.mark.asyncio
async def test_inspector_records_with_existing_session(db_session):
    repo_factory = lambda session: InstrumentTokenUsageRepository(session)
    inspector = ToolsTokenUsageInspector(
        session=db_session,
        repository_factory=repo_factory,
        session_factory=lambda: _session_factory_provider(db_session),
    )

    await inspector.record(
        tool="vision_tool",
        task="media_image_analysis",
        model="gpt-4o",
        tokens_in=12,
        tokens_out=34,
        comment_id="comment-1",
        metadata={"source": "test"},
    )

    result = await db_session.execute(select(InstrumentTokenUsage))
    rows = result.scalars().all()

    assert len(rows) == 1
    entry = rows[0]
    assert entry.tool == "vision_tool"
    assert entry.task == "media_image_analysis"
    assert entry.tokens_in == 12
    assert entry.tokens_out == 34
    assert entry.comment_id == "comment-1"
    assert entry.details["source"] == "test"
    assert "recorded_at_utc" in entry.details


@pytest.mark.asyncio
async def test_inspector_opens_temporary_session(db_session):
    repo_factory = lambda session: InstrumentTokenUsageRepository(session)
    session_maker = _session_factory_provider(db_session)

    inspector = ToolsTokenUsageInspector(
        session=None,
        repository_factory=repo_factory,
        session_factory=lambda: session_maker,
    )

    await inspector.record(
        tool="embedding_service",
        task="generate_embedding",
        model="text-embedding-ada-002",
        tokens_in=None,
        tokens_out=None,
        comment_id=None,
        metadata=None,
    )

    async with session_maker() as check_session:
        result = await check_session.execute(select(InstrumentTokenUsage))
        rows = result.scalars().all()

    assert len(rows) == 1
    entry = rows[0]
    assert entry.tool == "embedding_service"
    assert entry.comment_id is None
    assert entry.tokens_in is None
    assert entry.tokens_out is None
    assert "recorded_at_utc" in entry.details
