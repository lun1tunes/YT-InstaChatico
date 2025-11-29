"""Pydantic schemas for answer generation."""

from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class AnswerResultData(BaseModel):
    """Answer generation result data."""

    model_config = ConfigDict(from_attributes=True)

    answer: str = Field(..., description="Generated answer text")
    answer_confidence: float | None = Field(None, ge=0.0, le=1.0, description="Answer confidence 0.0-1.0")
    answer_quality_score: int | None = Field(None, ge=0, le=100, description="Quality score 0-100")
    input_tokens: int | None = Field(None, description="Input tokens used")
    output_tokens: int | None = Field(None, description="Output tokens used")
    processing_time_ms: int | None = Field(None, description="Processing time in milliseconds")


class AnswerRequest(BaseModel):
    """Request model for answer generation."""

    model_config = ConfigDict(from_attributes=True)

    comment_id: str = Field(..., description="Instagram comment ID")
    comment_text: str = Field(..., min_length=1, description="Question text")
    username: str | None = Field(None, description="Username of commenter")
    media_id: str | None = Field(None, description="Instagram media ID")


class AnswerResponse(BaseModel):
    """Response model for answer generation."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Processing status")
    comment_id: str = Field(..., description="Instagram comment ID")
    answer: str | None = Field(None, description="Generated answer text")
    answer_confidence: float | None = Field(None, ge=0.0, le=1.0, description="Answer confidence")
    answer_quality_score: int | None = Field(None, ge=0, le=100, description="Quality score")
    input_tokens: int | None = Field(None, description="Input tokens used")
    output_tokens: int | None = Field(None, description="Output tokens used")
    processing_time_ms: int | None = Field(None, description="Processing time in milliseconds")
    processing_started_at: datetime | None = Field(None, description="Processing start time")
    processing_completed_at: datetime | None = Field(None, description="Processing completion time")
    reply_sent: bool = Field(False, description="Whether reply was sent to Instagram")
    reply_id: str | None = Field(None, description="Instagram reply ID")
    error: str | None = Field(None, description="Error message if failed")
