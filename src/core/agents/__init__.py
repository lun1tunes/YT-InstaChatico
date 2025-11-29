# OpenAI Agents SDK integration for Instagram comment processing

from .agent_comment_classification import (
    create_comment_classification_agent,
    get_comment_classification_agent,
    comment_classification_agent,  # Singleton instance
    ClassificationResult,
)

from .agent_comment_response import (
    create_comment_response_agent,
    get_comment_response_agent,
    comment_response_agent,  # Singleton instance
    AnswerResult,
)

__all__ = [
    # Classification agents
    "create_comment_classification_agent",
    "get_comment_classification_agent",
    "comment_classification_agent",  # Singleton instance
    "ClassificationResult",
    # Response agents
    "create_comment_response_agent",
    "get_comment_response_agent",
    "comment_response_agent",  # Singleton instance
    "AnswerResult",
]
