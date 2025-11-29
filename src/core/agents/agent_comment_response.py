"""Instagram comment response agent with embedding search tool"""

import logging
from typing import Literal

from agents import Agent
from pydantic import BaseModel, Field

from ..config import settings
from .instructions.instruction_response import RESPONSE_INSTRUCTIONS
from .tools import embedding_search, document_context

logger = logging.getLogger(__name__)


class AnswerResult(BaseModel):
    """Pydantic model for comment response generation results"""

    answer: str = Field(description="The generated answer to the customer's question")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    reasoning: str = Field(description="Brief explanation of the answer approach and quality assessment")
    quality_score: int = Field(ge=0, le=100, description="Quality score from 0 to 100")
    is_helpful: bool = Field(description="Whether the answer is likely to be helpful to the customer")
    contains_contact_info: bool = Field(description="Whether the answer includes contact information or next steps")
    tone: Literal["professional", "friendly", "formal", "casual"] = Field(description="The tone of the response")


def create_comment_response_agent() -> Agent:
    """Create response agent with embedding search tool"""
    # Load instructions from external file for better security and maintainability
    enhanced_instructions = RESPONSE_INSTRUCTIONS

    # Create and return the configured agent with all tools:
    # - embedding_search: For product/service prices (ONLY source of price info)
    # - document_context: For business info (hours, location, promotions, policies)
    return Agent(
        name="InstagramCommentResponder",
        instructions=enhanced_instructions,
        output_type=AnswerResult,
        model=settings.openai.model_comment_response,
        tools=[embedding_search, document_context],
    )


# Convenience function to get a pre-configured agent
def get_comment_response_agent() -> Agent:
    """Get pre-configured response agent instance"""
    return create_comment_response_agent()


# Create a singleton instance of the agent
# This ensures only one instance is created and reused throughout the application
comment_response_agent = create_comment_response_agent()
