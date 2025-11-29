"""
Unit tests for AgentExecutor.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.services.agent_executor import AgentExecutor


@pytest.mark.unit
@pytest.mark.service
class TestAgentExecutor:
    """Validate AgentExecutor behaviour."""

    @patch("core.services.agent_executor.Runner.run", new_callable=AsyncMock)
    async def test_run_delegates_to_runner(self, mock_runner_run):
        """AgentExecutor should proxy calls to Runner.run with same args."""
        executor = AgentExecutor()
        mock_result = MagicMock()
        mock_runner_run.return_value = mock_result

        result = await executor.run("fake_agent", input="hello", session="sess")

        mock_runner_run.assert_awaited_once_with("fake_agent", input="hello", session="sess")
        assert result is mock_result
