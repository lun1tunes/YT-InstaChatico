import logging
import time
from typing import Any, Dict, Optional

from .base_service import BaseService
from ..agents import get_comment_response_agent
from ..config import settings
from ..schemas.answer import AnswerResponse
from ..interfaces.agents import IAgentExecutor, IAgentSessionService

logger = logging.getLogger(__name__)


class QuestionAnswerService(BaseService):
    """Generate answers using OpenAI Agents SDK, reuses sessions from classification."""

    def __init__(
        self,
        api_key: str = None,
        db_path: str = "conversations/conversations.db",
        agent_executor: Optional[IAgentExecutor] = None,
        session_service: Optional[IAgentSessionService] = None,
    ):
        super().__init__(db_path, session_service=session_service)
        self.api_key = api_key or settings.openai.api_key
        self.response_agent = get_comment_response_agent()
        if agent_executor is None:
            from .agent_executor import AgentExecutor

            self.agent_executor: IAgentExecutor = AgentExecutor()
        else:
            self.agent_executor = agent_executor

    async def generate_answer(
        self,
        question_text: str,
        conversation_id: Optional[str] = None,
        media_context: Optional[Dict[str, Any]] = None,
        username: Optional[str] = None,
    ) -> AnswerResponse:
        """Generate answer for customer question with session context."""
        start_time = time.time()

        try:
            # Sanitize input
            sanitized_text = self._sanitize_input(question_text)

            # Add username attribution for multi-user conversation tracking
            if username:
                sanitized_text = f"@{username}: {sanitized_text}"

            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."

            # Use session if conversation_id is provided
            if conversation_id:
                logger.debug(
                    f"Starting answer generation with persistent session for conversation_id: {conversation_id}"
                )
                # Use SQLiteSession (media context already injected by classification service)
                session = self.session_service.get_session(conversation_id)
                result = await self.agent_executor.run(
                    self.response_agent, input=sanitized_text, session=session
                )
                logger.info(
                    f"Answer generated successfully using SQLiteSession for conversation: {conversation_id}"
                )
            else:
                logger.debug(
                    "Starting answer generation without session (stateless mode)"
                )
                # Use regular Runner without session
                result = await self.agent_executor.run(self.response_agent, input=sanitized_text)
                logger.info("Answer generated successfully without session")

            answer_result = result.final_output
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Extract token usage from raw_responses (OpenAI Agents SDK structure)
            input_tokens = None
            output_tokens = None
            tokens_used = None

            # OpenAI Agents SDK stores usage in raw_responses[0].usage, not result.usage
            if hasattr(result, 'raw_responses') and result.raw_responses:
                first_response = result.raw_responses[0]
                if hasattr(first_response, 'usage') and first_response.usage:
                    usage = first_response.usage
                    input_tokens = getattr(usage, 'input_tokens', None)
                    output_tokens = getattr(usage, 'output_tokens', None)
                    if input_tokens and output_tokens:
                        tokens_used = input_tokens + output_tokens

                    logger.debug(f"Token usage - Input: {input_tokens}, Output: {output_tokens}, Total: {tokens_used}")
                else:
                    logger.debug("No usage data in raw_responses[0]")
            else:
                logger.debug("No raw_responses available for token extraction")

            # Fallback to estimation if usage not available
            if tokens_used is None:
                tokens_used = self._estimate_tokens(sanitized_text + answer_result.answer)
                logger.debug(f"Token usage estimated: {tokens_used}")

            if conversation_id:
                await self._append_exchange_to_session(
                    conversation_id=conversation_id,
                    user_message=sanitized_text,
                    assistant_message=answer_result.answer,
                )

            return AnswerResponse(
                status="success",
                comment_id=conversation_id or "unknown",
                answer=answer_result.answer,
                answer_confidence=answer_result.confidence,
                answer_quality_score=answer_result.quality_score,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                processing_time_ms=processing_time_ms,
                error=None,
            )

        except Exception as e:
            logger.error(f"Answer generation error: {e}")
            return self._create_error_response(str(e))

    def _create_error_response(self, error_message: str) -> AnswerResponse:
        """Return error response with metadata."""
        return AnswerResponse(
            status="error",
            comment_id="unknown",
            answer=None,
            answer_confidence=0.0,
            answer_quality_score=0,
            processing_time_ms=0,
            error=error_message,
        )

    async def _append_exchange_to_session(
        self,
        *,
        conversation_id: str,
        user_message: str | None,
        assistant_message: str,
    ) -> None:
        """Persist the latest user/assistant turn into the shared conversation session."""
        if not assistant_message:
            return

        try:
            session = self.session_service.get_session(conversation_id)
            items = []
            if user_message:
                items.append({"role": "user", "content": user_message})
            items.append({"role": "assistant", "content": assistant_message})
            await session.add_items(items)
            logger.debug(
                "Conversation exchange appended | conversation_id=%s | user_added=%s",
                conversation_id,
                bool(user_message),
            )
        except Exception as exc:
            logger.warning(
                "Failed to append exchange to conversation | conversation_id=%s | error=%s",
                conversation_id,
                exc,
            )
