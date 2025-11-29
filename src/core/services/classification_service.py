import logging
from typing import Any, Dict, Optional

from .base_service import BaseService
from ..agents import comment_classification_agent
from ..config import settings
from ..schemas.classification import ClassificationResponse
from ..interfaces.agents import IAgentExecutor, IAgentSessionService, IAgentSession

logger = logging.getLogger(__name__)


class CommentClassificationService(BaseService):
    """Classify YouTube video comments using OpenAI Agents SDK with persistent sessions."""

    def __init__(
        self,
        api_key: str = None,
        db_path: str = "conversations/conversations.db",
        agent_executor: Optional[IAgentExecutor] = None,
        session_service: Optional[IAgentSessionService] = None,
    ):
        super().__init__(db_path, session_service=session_service)
        self.api_key = api_key or settings.openai.api_key
        self.classification_agent = comment_classification_agent
        if agent_executor is None:
            from .agent_executor import AgentExecutor

            self.agent_executor: IAgentExecutor = AgentExecutor()
        else:
            self.agent_executor = agent_executor

    async def _get_session_with_media_context(
        self, conversation_id: str, media_context: Optional[Dict[str, Any]] = None
    ) -> IAgentSession:
        """Get or create session, inject media context once on first message."""
        logger.debug(f"Preparing agent session for conversation_id: {conversation_id}")

        if media_context:
            media_description = self._create_media_description(media_context)
            context_items = [
                {
                    "role": "system",
                    "content": (
                        "📋 MEDIA CONTEXT (YouTube Video):\n"
                        f"{media_description}\n\nUse this context when analyzing comments and generating responses."
                    ),
                }
            ]
            session = await self.session_service.ensure_context(conversation_id, context_items)
            logger.info(f"✅ Media context ensured for conversation: {conversation_id}")
        else:
            session = self.session_service.get_session(conversation_id)

        logger.debug(f"Agent session ready for conversation: {conversation_id}")
        return session

    def _create_media_description(self, media_context: Dict[str, Any]) -> str:
        """Format media context into readable description."""
        description_parts = []

        title = media_context.get("title") or media_context.get("caption")
        if title:
            description_parts.append(f"Название видео: {title}")

        channel = media_context.get("username") or media_context.get("channel_title")
        if channel:
            description_parts.append(f"Канал: {channel}")

        if media_context.get("caption"):
            caption = media_context["caption"]
            if len(caption) > 500:
                caption = caption[:500] + "..."
            description_parts.append(f"Описание: {caption}")

        if media_context.get("permalink"):
            description_parts.append(f"Ссылка на видео: {media_context['permalink']}")

        if media_context.get("media_url"):
            description_parts.append(f"Превью: {media_context['media_url']}")

        if media_context.get("posted_at"):
            description_parts.append(f"Опубликовано: {media_context['posted_at']}")

        engagement_parts = []
        if media_context.get("comments_count") is not None:
            engagement_parts.append(f"{media_context['comments_count']} комментариев")
        if media_context.get("like_count") is not None:
            engagement_parts.append(f"{media_context['like_count']} отметок \"нравится\"")
        if media_context.get("view_count") is not None:
            engagement_parts.append(f"{media_context['view_count']} просмотров")

        if engagement_parts:
            description_parts.append(f"Статистика: {', '.join(engagement_parts)}")

        return "\n".join(description_parts)

    def generate_conversation_id(self, comment_id: str, parent_id: Optional[str] = None) -> str:
        """Generate conversation ID: first_question_comment_{parent_id or comment_id}."""
        if parent_id:
            # If this is a reply, use the parent's conversation ID
            return f"first_question_comment_{parent_id}"
        else:
            # If this is a top-level comment, use its own ID
            return f"first_question_comment_{comment_id}"

    async def classify_comment(
        self,
        comment_text: str,
        conversation_id: Optional[str] = None,
        media_context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResponse:
        """Classify comment using OpenAI agent with optional session context."""
        try:
            # Format input with conversation and media context
            formatted_input = self._format_input_with_context(comment_text, conversation_id, media_context)

            if len(formatted_input) > 2000:  # Increased limit for context
                formatted_input = formatted_input[:2000] + "..."
                logger.warning(f"Input truncated to 2000 characters: {comment_text[:50]}...")

            logger.info(f"Classifying comment with context: {formatted_input[:200]}...")

            # Use session if conversation_id is provided
            if conversation_id:
                logger.debug(f"Starting classification with persistent session for conversation_id: {conversation_id}")
                # Use SQLiteSession with media context for persistent conversation
                session = await self._get_session_with_media_context(conversation_id, media_context)
                result = await self.agent_executor.run(
                    self.classification_agent, input=formatted_input, session=session
                )
                logger.info(
                    f"Classification completed using SQLiteSession with media context for conversation: {conversation_id}"
                )
            else:
                logger.debug("Starting classification without session (stateless mode)")
                # Use regular Runner without session
                result = await self.agent_executor.run(self.classification_agent, input=formatted_input)
                logger.info("Classification completed without session")

            # Extract the final output from the result
            classification_result = result.final_output

            # Extract token usage from raw_responses (OpenAI Agents SDK structure)
            input_tokens = None
            output_tokens = None

            # OpenAI Agents SDK stores usage in raw_responses[0].usage, not result.usage
            if hasattr(result, "raw_responses") and result.raw_responses:
                first_response = result.raw_responses[0]
                if hasattr(first_response, "usage") and first_response.usage:
                    usage = first_response.usage
                    input_tokens = getattr(usage, "input_tokens", None)
                    output_tokens = getattr(usage, "output_tokens", None)

                    logger.debug(f"Token usage - Input: {input_tokens}, Output: {output_tokens}")
                else:
                    logger.debug("No usage data in raw_responses[0]")
            else:
                logger.debug("No raw_responses available for token extraction")

            logger.info(
                f"Classification result: {classification_result.type} (confidence: {classification_result.confidence})"
            )

            return ClassificationResponse(
                status="success",
                comment_id=conversation_id or "unknown",
                type=classification_result.type,
                confidence=classification_result.confidence,
                reasoning=classification_result.reasoning,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=None,
            )

        except Exception as e:
            logger.error(f"Classification error: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return self._create_error_response(str(e))

    def _format_input_with_context(
        self,
        comment_text: str,
        conversation_id: Optional[str] = None,
        media_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format comment with media context and conversation info."""
        sanitized_text = self._sanitize_input(comment_text)

        # Build context information
        context_parts = []

        # Add media context if available
        if media_context:
            media_info = []
            if media_context.get("caption"):
                media_info.append(f"Post caption: {media_context['caption'][:200]}...")
            if media_context.get("media_type"):
                media_info.append(f"Post type: {media_context['media_type']}")
            if media_context.get("media_context"):
                # AI-analyzed image description
                media_info.append(f"Image analysis: {media_context['media_context'][:500]}...")
            if media_context.get("username"):
                media_info.append(f"Post author: @{media_context['username']}")
            if media_context.get("comments_count") is not None:
                media_info.append(f"Post has {media_context['comments_count']} comments")
            if media_context.get("like_count") is not None:
                media_info.append(f"Post has {media_context['like_count']} likes")

            if media_info:
                context_parts.append("Media context:")
                context_parts.extend(media_info)

        # Add conversation context if available
        if conversation_id:
            context_parts.append(f"Conversation ID: {conversation_id}")

        # Combine all context
        if context_parts:
            context_text = "\n".join(context_parts)
            formatted_input = f"{context_text}\n\nComment to classify: {sanitized_text}"
            logger.debug(f"Formatted input with context: {formatted_input[:200]}...")
            return formatted_input

        # Return sanitized text without context
        return sanitized_text

    def _create_error_response(self, error_message: str) -> ClassificationResponse:
        """Return safe fallback response on classification error."""
        return ClassificationResponse(
            status="error",
            comment_id="unknown",
            type="spam / irrelevant",  # Safe fallback
            confidence=0,
            reasoning=f"Classification failed: {error_message}",
            error=error_message,
        )
