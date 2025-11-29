"""Pydantic schemas for webhook responses."""

from pydantic import BaseModel, Field, ConfigDict


class WebhookProcessingResponse(BaseModel):
    """Response for webhook processing."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Processing status (success/error)")
    message: str = Field(..., description="Status message")
    comment_id: str | None = Field(None, description="Instagram comment ID")
    classification: str | None = Field(None, description="Comment classification")
    task_id: str | None = Field(None, description="Celery task ID")


class TestCommentResponse(BaseModel):
    """Response for test comment endpoint."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Test status")
    message: str = Field(..., description="Test result message")
    comment_id: str | None = Field(None, description="Test comment ID")
    classification: str | None = Field(None, description="Comment classification")
    answer: str | None = Field(None, description="Generated answer if applicable")
    processing_details: dict | None = Field(None, description="Additional processing details")
