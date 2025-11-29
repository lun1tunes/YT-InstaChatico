"""
Default agent executor implementation using OpenAI Agents SDK.
"""

from typing import Any

from agents import Runner

from core.interfaces.agents import IAgentExecutor, AgentRunResult


class AgentExecutor(IAgentExecutor):
    """Thin wrapper around Runner.run to allow DI-friendly swapping."""

    async def run(self, agent: Any, *, input: str, session: Any | None = None) -> AgentRunResult:
        return await Runner.run(agent, input=input, session=session)
