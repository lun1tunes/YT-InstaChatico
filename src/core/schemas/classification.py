"""Pydantic schemas for comment classification."""

from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ClassificationResultData(BaseModel):
    """Classification result data."""

    model_config = ConfigDict(from_attributes=True)

    type: str = Field(..., description="Classification category")
    confidence: int = Field(..., ge=0, le=100, description="Confidence score 0-100")
    reasoning: str | None = Field(None, description="AI reasoning for classification")
    input_tokens: int | None = Field(None, description="Input tokens used")
    output_tokens: int | None = Field(None, description="Output tokens used")


class ClassificationRequest(BaseModel):
    """Request model for comment classification."""

    model_config = ConfigDict(from_attributes=True)

    comment_id: str = Field(..., description="Instagram comment ID")
    comment_text: str = Field(..., min_length=1, description="Comment text to classify")
    username: str | None = Field(None, description="Username of commenter")
    media_id: str | None = Field(None, description="Instagram media ID")


class ClassificationResponse(BaseModel):
    """Response model for comment classification."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Processing status")
    comment_id: str = Field(..., description="Instagram comment ID")
    type: str | None = Field(None, description="Classification category")
    confidence: int | None = Field(None, ge=0, le=100, description="Confidence score 0-100")
    reasoning: str | None = Field(None, description="AI reasoning")
    input_tokens: int | None = Field(None, description="Input tokens used")
    output_tokens: int | None = Field(None, description="Output tokens used")
    processing_started_at: datetime | None = Field(None, description="Processing start time")
    processing_completed_at: datetime | None = Field(None, description="Processing completion time")
    error: str | None = Field(None, description="Error message if failed")
