"""Pydantic schemas for Instagram comment management."""

from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


# ============================================================================
# Base Schemas (DRY - reusable components)
# ============================================================================

class CommentBase(BaseModel):
    """Base comment fields - reused across all comment schemas."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Instagram comment ID")
    text: str = Field(..., description="Comment text")
    username: str = Field(..., description="Username of commenter")
    user_id: str = Field(..., description="Instagram user ID")
    media_id: str = Field(..., description="Instagram media ID")
    created_at: datetime = Field(..., description="Comment creation time")


class HidingInfoBase(BaseModel):
    """Base hiding information - reused across schemas."""

    model_config = ConfigDict(from_attributes=True)

    is_hidden: bool = Field(..., description="Whether comment is hidden on Instagram")
    hidden_at: datetime | None = Field(None, description="When comment was hidden")


class ClassificationInfoBase(BaseModel):
    """Base classification information - reused across schemas."""

    model_config = ConfigDict(from_attributes=True)

    classification: str | None = Field(None, description="Classification category")
    confidence: int | None = Field(None, ge=0, le=100, description="Confidence score 0-100")
    reasoning: str | None = Field(None, description="AI reasoning for classification")


class AnswerInfoBase(BaseModel):
    """Base answer information - reused across schemas."""

    model_config = ConfigDict(from_attributes=True)

    answer: str | None = Field(None, description="Generated answer text")
    answer_confidence: float | None = Field(None, ge=0.0, le=1.0, description="Answer confidence")
    answer_quality_score: int | None = Field(None, ge=0, le=100, description="Answer quality score")


class ReplyInfoBase(BaseModel):
    """Base reply information - reused across schemas."""

    model_config = ConfigDict(from_attributes=True)

    reply_sent: bool = Field(False, description="Whether reply was sent to Instagram")
    reply_sent_at: datetime | None = Field(None, description="When reply was sent")
    reply_status: str | None = Field(None, description="Reply status (sent/failed/pending)")
    reply_id: str | None = Field(None, description="Instagram reply ID")


class TokenUsageBase(BaseModel):
    """Base token usage information - reused across schemas."""

    model_config = ConfigDict(from_attributes=True)

    input_tokens: int | None = Field(None, description="Input tokens used")
    output_tokens: int | None = Field(None, description="Output tokens used")


# ============================================================================
# Detailed Response Schemas (composed from base schemas)
# ============================================================================

class CommentDetailResponse(CommentBase, HidingInfoBase):
    """Detailed comment information with hiding status."""

    parent_id: str | None = Field(None, description="Parent comment ID if this is a reply")
    conversation_id: str | None = Field(None, description="Conversation ID for threading")


class CommentWithClassificationResponse(CommentDetailResponse, ClassificationInfoBase, TokenUsageBase):
    """Comment with classification details."""

    processing_status: str | None = Field(None, description="Classification processing status")
    processing_started_at: datetime | None = Field(None, description="When classification started")
    processing_completed_at: datetime | None = Field(None, description="When classification completed")


class CommentWithAnswerResponse(CommentDetailResponse, AnswerInfoBase, TokenUsageBase):
    """Comment with answer details."""

    processing_status: str | None = Field(None, description="Answer processing status")
    processing_started_at: datetime | None = Field(None, description="When answer generation started")
    processing_completed_at: datetime | None = Field(None, description="When answer generation completed")


class CommentFullResponse(
    CommentDetailResponse,
    ClassificationInfoBase,
    AnswerInfoBase,
    ReplyInfoBase
):
    """Complete comment information with all related data."""

    # Classification details
    classification_status: str | None = Field(None, description="Classification processing status")
    classification_started_at: datetime | None = Field(None, description="Classification start time")
    classification_completed_at: datetime | None = Field(None, description="Classification completion time")
    classification_input_tokens: int | None = Field(None, description="Tokens used for classification")
    classification_output_tokens: int | None = Field(None, description="Tokens generated for classification")

    # Answer details
    answer_status: str | None = Field(None, description="Answer processing status")
    answer_started_at: datetime | None = Field(None, description="Answer generation start time")
    answer_completed_at: datetime | None = Field(None, description="Answer generation completion time")
    answer_input_tokens: int | None = Field(None, description="Tokens used for answer")
    answer_output_tokens: int | None = Field(None, description="Tokens generated for answer")
    answer_processing_time_ms: int | None = Field(None, description="Answer processing time in ms")


# ============================================================================
# Request Schemas
# ============================================================================

class HideCommentRequest(BaseModel):
    """Request to hide a comment."""

    model_config = ConfigDict(from_attributes=True)

    comment_id: str = Field(..., description="Instagram comment ID to hide")


class UnhideCommentRequest(BaseModel):
    """Request to unhide a comment."""

    model_config = ConfigDict(from_attributes=True)

    comment_id: str = Field(..., description="Instagram comment ID to unhide")


class SendReplyRequest(BaseModel):
    """Request to send a manual reply to a comment."""

    model_config = ConfigDict(from_attributes=True)

    comment_id: str = Field(..., description="Instagram comment ID to reply to")
    message: str = Field(..., min_length=1, max_length=500, description="Reply message text")


# ============================================================================
# Action Response Schemas
# ============================================================================

class HideCommentResponse(BaseModel):
    """Response for hide comment action."""

    model_config = ConfigDict(from_attributes=True)

    status: Literal["queued", "already_hidden", "error"] = Field(..., description="Action status")
    message: str = Field(..., description="Status message")
    comment_id: str = Field(..., description="Instagram comment ID")
    task_id: str | None = Field(None, description="Celery task ID if queued")
    hidden_at: datetime | None = Field(None, description="When comment was hidden (if already hidden)")


class UnhideCommentResponse(BaseModel):
    """Response for unhide comment action."""

    model_config = ConfigDict(from_attributes=True)

    status: Literal["success", "not_hidden", "error"] = Field(..., description="Action status")
    message: str = Field(..., description="Status message")
    comment_id: str = Field(..., description="Instagram comment ID")


class SendReplyResponse(BaseModel):
    """Response for manual reply sending."""

    model_config = ConfigDict(from_attributes=True)

    status: Literal["queued", "success", "error"] = Field(..., description="Action status")
    message: str = Field(..., description="Status message")
    comment_id: str = Field(..., description="Instagram comment ID")
    task_id: str | None = Field(None, description="Celery task ID if queued")
    reply_text: str | None = Field(None, description="The reply message sent")


# ============================================================================
# List Response Schemas
# ============================================================================

class CommentListItem(CommentBase, HidingInfoBase, ClassificationInfoBase):
    """Compact comment info for list views."""

    parent_id: str | None = Field(None, description="Parent comment ID if reply")
    reply_sent: bool = Field(False, description="Whether reply was sent")


class CommentListResponse(BaseModel):
    """Paginated list of comments."""

    model_config = ConfigDict(from_attributes=True)

    comments: list[CommentListItem] = Field(..., description="List of comments")
    total: int = Field(..., ge=0, description="Total number of comments")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
