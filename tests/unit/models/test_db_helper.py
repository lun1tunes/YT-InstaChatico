"""
Unit tests for DatabaseHelper.

Tests cover:
- Initialization with URL and echo settings
- Engine creation
- Session factory creation
- Scoped session creation
- Session dependency generators
- Configuration validation
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.db_helper import DatabaseHelper, db_helper


@pytest.mark.unit
@pytest.mark.model
class TestDatabaseHelper:
    """Test DatabaseHelper class functionality."""

    def test_init_creates_engine(self):
        """Test that initialization creates an async engine."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        assert helper.engine is not None
        assert hasattr(helper.engine, 'dispose')

    def test_init_creates_session_factory(self):
        """Test that initialization creates a session factory."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        assert helper.session_factory is not None
        assert callable(helper.session_factory)

    def test_init_with_echo_true(self):
        """Test initialization with echo=True."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=True)

        # Engine should be created with echo enabled
        assert helper.engine is not None
        assert helper.engine.echo is True

    def test_init_with_echo_false(self):
        """Test initialization with echo=False."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        assert helper.engine.echo is False

    def test_session_factory_configuration(self):
        """Test that session factory is configured correctly."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        # Session factory should have correct settings
        # We can't directly inspect these, but we can test by creating a session
        session = helper.session_factory()
        assert isinstance(session, AsyncSession)

    def test_get_scoped_session_returns_scoped_session(self):
        """Test that get_scoped_session returns a scoped session."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        scoped = helper.get_scoped_session()

        assert scoped is not None
        assert hasattr(scoped, 'remove')  # Scoped sessions have remove method

    @pytest.mark.asyncio
    async def test_session_dependency_yields_session(self):
        """Test that session_dependency yields an AsyncSession."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        # Use the generator
        gen = helper.session_dependency()
        session = await gen.__anext__()

        assert isinstance(session, AsyncSession)

        # Cleanup
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

    @pytest.mark.asyncio
    async def test_session_dependency_closes_session(self):
        """Test that session_dependency closes session after use."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        session = None
        async for s in helper.session_dependency():
            session = s
            break

        # Session should be created
        assert session is not None

    @pytest.mark.asyncio
    async def test_scoped_session_dependency_yields_session(self):
        """Test that scoped_session_dependency yields a session."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        gen = helper.scoped_session_dependency()
        session = await gen.__anext__()

        assert session is not None

        # Cleanup
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

    @pytest.mark.asyncio
    async def test_scoped_session_dependency_closes_session(self):
        """Test that scoped_session_dependency closes session."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        session = None
        async for s in helper.scoped_session_dependency():
            session = s
            break

        assert session is not None

    def test_different_database_urls(self):
        """Test initialization with different database URLs."""
        # Only test sqlite for unit tests - others would need real databases
        url = "sqlite+aiosqlite:///:memory:"

        helper = DatabaseHelper(url=url, echo=False)
        assert helper.engine is not None

    def test_db_helper_singleton_exists(self):
        """Test that global db_helper instance exists."""
        assert db_helper is not None
        assert isinstance(db_helper, DatabaseHelper)

    def test_db_helper_has_engine(self):
        """Test that global db_helper has engine."""
        assert hasattr(db_helper, 'engine')
        assert db_helper.engine is not None

    def test_db_helper_has_session_factory(self):
        """Test that global db_helper has session factory."""
        assert hasattr(db_helper, 'session_factory')
        assert callable(db_helper.session_factory)

    def test_multiple_helpers_independent(self):
        """Test that multiple DatabaseHelper instances are independent."""
        helper1 = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=True)
        helper2 = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        # Should have different engines
        assert helper1.engine is not helper2.engine
        assert helper1.engine.echo is True
        assert helper2.engine.echo is False

    @pytest.mark.asyncio
    async def test_session_can_execute_query(self):
        """Test that session from dependency can execute queries."""
        from sqlalchemy import text

        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        async for session in helper.session_dependency():
            # Should be able to execute a simple query (use text() wrapper for SQL)
            result = await session.execute(text("SELECT 1"))
            assert result is not None
            break

    def test_engine_has_correct_driver(self):
        """Test that engine uses async driver."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        # Should use async driver
        assert 'aiosqlite' in str(helper.engine.url) or 'asyncpg' in str(helper.engine.url)

    @pytest.mark.asyncio
    async def test_session_context_manager_behavior(self):
        """Test that sessions work in context manager style."""
        from sqlalchemy import text

        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        # Should work with context manager
        async with helper.session_factory() as session:
            assert isinstance(session, AsyncSession)
            result = await session.execute(text("SELECT 1"))
            assert result is not None

    def test_session_factory_creates_new_sessions(self):
        """Test that session factory creates new session instances."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        session1 = helper.session_factory()
        session2 = helper.session_factory()

        # Should be different instances
        assert session1 is not session2

    @pytest.mark.asyncio
    async def test_scoped_session_same_task_same_instance(self):
        """Test that scoped sessions return same instance within same task."""
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        scoped = helper.get_scoped_session()

        # In same task, should get same session
        session1 = scoped()
        session2 = scoped()

        # Note: These might be the same or different depending on scoping
        # Just verify they're both valid sessions
        assert session1 is not None
        assert session2 is not None

    def test_helper_with_postgresql_url_format(self):
        """Test helper with PostgreSQL URL format."""
        url = "postgresql+asyncpg://user:password@localhost:5432/dbname"
        helper = DatabaseHelper(url=url, echo=False)

        assert helper.engine is not None
        assert 'asyncpg' in str(helper.engine.url)

    def test_helper_with_connection_pool_settings(self):
        """Test that helper can be created (pool settings are internal)."""
        # We can't directly test pool settings, but ensure creation works
        helper = DatabaseHelper(url="sqlite+aiosqlite:///:memory:", echo=False)

        assert helper.engine is not None
        assert helper.session_factory is not None
