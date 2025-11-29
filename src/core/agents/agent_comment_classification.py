"""
Instagram Comment Classification Agent

This module contains the OpenAI Agent configuration for classifying Instagram comments
into business-relevant categories. The agent is designed to provide accurate and
consistent classification with multi-language support.
"""

from typing import Literal

from agents import Agent
from pydantic import BaseModel, Field

from ..config import settings
from .instructions.instruction_classification import CLASSIFICATION_INSTRUCTIONS


class ClassificationResult(BaseModel):
    """Pydantic model for structured classification output using OpenAI Agents SDK"""

    type: Literal[
        "positive feedback",
        "critical feedback",
        "urgent issue / complaint",
        "question / inquiry",
        "partnership proposal",
        "toxic / abusive",
        "spam / irrelevant",
    ] = Field(description="The classification category for the comment")
    confidence: int = Field(ge=0, le=100, description="Confidence score from 0 to 100")
    reasoning: str = Field(
        description="Brief explanation of why this classification was chosen, including context considerations"
    )
    context_used: bool = Field(
        default=False, description="Whether conversation context was available and used in classification"
    )
    conversation_continuity: bool = Field(
        default=False, description="Whether this comment continues or relates to previous conversation"
    )


def create_comment_classification_agent(api_key: str = None) -> Agent:
    """
    Create and configure the Instagram comment classification agent.

    Args:
        api_key: OpenAI API key (optional, uses settings if not provided)

    Returns:
        Configured Agent instance for comment classification
    """

    # Load instructions from external file for better security and maintainability
    enhanced_instructions = CLASSIFICATION_INSTRUCTIONS

    # Create and return the configured agent
    return Agent(
        name="InstagramCommentClassifier",
        instructions=enhanced_instructions,
        output_type=ClassificationResult,
        model=settings.openai.model_comment_classification,
    )


# Convenience function to get a pre-configured agent
def get_comment_classification_agent() -> Agent:
    """
    Get a pre-configured comment classification agent using default settings.

    Returns:
        Configured Agent instance for comment classification
    """
    return create_comment_classification_agent()


# Create a singleton instance of the agent
# This ensures only one instance is created and reused throughout the application
comment_classification_agent = create_comment_classification_agent()
