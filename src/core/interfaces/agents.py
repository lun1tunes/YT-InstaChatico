"""
Agent-related protocol interfaces to decouple LLM runner and session management.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, Sequence


class AgentRunUsage(Protocol):
    """Protocol describing token usage returned by agent providers."""

    input_tokens: Optional[int]
    output_tokens: Optional[int]


class AgentRawResponse(Protocol):
    """Protocol for raw responses that may carry usage metadata."""

    usage: Optional[AgentRunUsage]


class AgentRunResult(Protocol):
    """Minimal information required from an agent execution result."""

    final_output: Any
    raw_responses: Optional[Sequence[AgentRawResponse]]


class IAgentExecutor(Protocol):
    """Execute LLM agents and return standardized results."""

    async def run(
        self,
        agent: Any,
        *,
        input: str,
        session: Any | None = None,
    ) -> AgentRunResult:
        ...


class IAgentSession(Protocol):
    """Protocol representing a persisted agent session."""

    async def add_items(self, items: List[dict]) -> None:
        ...


class IAgentSessionService(Protocol):
    """Manage agent sessions and contextual system messages."""

    def get_session(self, conversation_id: str) -> IAgentSession:
        ...

    async def has_messages(self, conversation_id: str) -> bool:
        ...

    async def ensure_context(self, conversation_id: str, context_items: List[dict]) -> IAgentSession:
        ...
