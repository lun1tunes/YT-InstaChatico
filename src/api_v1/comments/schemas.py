"""Pydantic schemas for the JSON API contract."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator, ConfigDict


class MediaUpdateRequest(BaseModel):
    context: Optional[str] = Field(default=None, description="Override AI description of the post")
    is_comment_enabled: Optional[bool] = Field(default=None, description="Allow or disallow new comments")
    is_processing_enabled: Optional[bool] = Field(default=None, description="Toggle automated processing")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "MediaUpdateRequest":
        if all(
            value is None
            for value in (
                self.context,
                self.is_comment_enabled,
                self.is_processing_enabled,
            )
        ):
            raise ValueError("At least one field must be provided")
        return self


class ClassificationUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str | int | None = Field(
        default=None,
        description="Classification label/string",
    )
    classification_type: str | int | None = Field(
        default=None,
        alias="classification_type",
        description="Alias for classification label/string",
    )
    reasoning: str = Field(..., description="Manual reasoning for the change")

    @model_validator(mode="after")
    def ensure_reasoning(self) -> "ClassificationUpdateRequest":
        if not self.reasoning.strip():
            raise ValueError("Reasoning cannot be empty")
        raw_type = self.type if self.type is not None else self.classification_type
        if raw_type is None:
            raise ValueError("Classification type is required")
        normalized = str(raw_type).strip()
        if not normalized:
            raise ValueError("Classification type cannot be empty")
        self.type = normalized
        self.classification_type = None
        return self


class AnswerUpdateRequest(BaseModel):
    answer: str = Field(..., description="Updated answer text")
    quality_score: Optional[int] = Field(default=None, ge=0, le=100)
    confidence: Optional[int] = Field(default=None, ge=0, le=100, description="Confidence in integer percent")


class AnswerCreateRequest(BaseModel):
    answer: str = Field(..., description="Manual answer text")


class ErrorDetail(BaseModel):
    code: int
    message: str
    details: Optional[Any] = None


class SimpleMeta(BaseModel):
    error: Optional[ErrorDetail] = None


class PaginationMeta(SimpleMeta):
    page: int
    per_page: int
    total: int


class MediaQuickStats(BaseModel):
    positive_feedback_total: int = 0
    positive_feedback_increment: int = 0
    questions_total: int = 0
    questions_increment: int = 0
    negative_feedback_total: int = 0
    negative_feedback_increment: int = 0
    urgent_issues_total: int = 0
    urgent_issues_increment: int = 0
    partnership_proposals_total: int = 0
    partnership_proposals_increment: int = 0
    toxic_abusive_total: int = 0
    toxic_abusive_increment: int = 0
    spam_irrelevant_total: int = 0
    spam_irrelevant_increment: int = 0


class MediaDTO(BaseModel):
    id: str
    permalink: Optional[str] = None
    caption: Optional[str] = None
    url: Optional[str] = None
    type: Optional[int] = None
    context: Optional[str] = None
    children_urls: list[str] = Field(default_factory=list)
    comments_count: Optional[int] = None
    like_count: Optional[int] = None
    shortcode: Optional[str] = None
    posted_at: Optional[str] = None
    is_comment_enabled: Optional[bool] = None
    is_processing_enabled: bool
    stats: Optional[MediaQuickStats] = None


class ClassificationDTO(BaseModel):
    id: Optional[int] = None
    processing_status: Optional[int] = None
    processing_completed_at: Optional[str] = None
    last_error: Optional[str] = None
    confidence: Optional[int] = None
    classification_type: Optional[int] = None
    reasoning: Optional[str] = None


class AnswerDTO(BaseModel):
    id: int
    processing_status: Optional[int] = None
    processing_completed_at: Optional[str] = None
    last_error: Optional[str] = None
    answer: Optional[str] = None
    confidence: Optional[int] = None
    quality_score: Optional[int] = None
    reply_sent: bool
    reply_status: Optional[str] = None
    reply_error: Optional[str] = None
    is_ai_generated: bool = True
    is_deleted: bool = False


class CommentDTO(BaseModel):
    id: str
    media_id: str
    parent_id: Optional[str] = None
    username: str
    text: str
    created_at: Optional[str] = None
    is_hidden: bool
    is_deleted: bool
    last_error: Optional[str] = None
    classification: Optional[ClassificationDTO] = None
    answers: list[AnswerDTO] = Field(default_factory=list)


class MediaListResponse(BaseModel):
    meta: PaginationMeta
    payload: list[MediaDTO]


class MediaResponse(BaseModel):
    meta: SimpleMeta
    payload: MediaDTO


class CommentListResponse(BaseModel):
    meta: PaginationMeta
    payload: list[CommentDTO]
    stats: Optional[MediaQuickStats] = None


class CommentResponse(BaseModel):
    meta: SimpleMeta
    payload: CommentDTO


class AnswerListResponse(BaseModel):
    meta: SimpleMeta
    payload: list[AnswerDTO]


class AnswerResponse(BaseModel):
    meta: SimpleMeta
    payload: AnswerDTO


class ClassificationTypeDTO(BaseModel):
    code: int
    label: str


class ClassificationTypesResponse(BaseModel):
    meta: SimpleMeta
    payload: list[ClassificationTypeDTO]


class EmptyResponse(BaseModel):
    meta: SimpleMeta
    payload: None = None


class ErrorResponse(BaseModel):
    meta: SimpleMeta
    payload: None = None


MediaListResponse.model_rebuild()
