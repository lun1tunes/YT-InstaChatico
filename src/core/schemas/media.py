"""Pydantic schemas for Media entities."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, ConfigDict


class MediaBase(BaseModel):
    """Base schema for Media with common fields."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Instagram media ID")
    permalink: str = Field(..., description="Instagram post permalink URL")
    caption: Optional[str] = Field(None, description="Post caption text")
    media_url: Optional[str] = Field(None, description="URL to the media file (first image for carousels)")
    media_type: Optional[str] = Field(None, description="Type of media (IMAGE, VIDEO, CAROUSEL_ALBUM)")
    children_media_urls: Optional[List[str]] = Field(
        None,
        description="Array of all media URLs for CAROUSEL_ALBUM (includes all children images/videos)"
    )
    media_context: Optional[str] = Field(None, description="AI-generated detailed description and context")
    comments_count: Optional[int] = Field(None, description="Number of comments on the post")
    like_count: Optional[int] = Field(None, description="Number of likes on the post")
    shortcode: Optional[str] = Field(None, description="Instagram shortcode")
    posted_at: Optional[datetime] = Field(None, description="When the media was posted")
    is_comment_enabled: Optional[bool] = Field(None, description="Whether comments are enabled")
    is_processing_enabled: Optional[bool] = Field(None, description="Whether automated processing is enabled")
    username: Optional[str] = Field(None, description="Username of the media owner")
    owner: Optional[str] = Field(None, description="Owner account ID")


class MediaResponse(MediaBase):
    """Response schema for Media with timestamps."""

    created_at: datetime = Field(..., description="When this record was created")
    updated_at: datetime = Field(..., description="When this record was last updated")


class MediaDetailResponse(MediaBase):
    """Detailed response schema for Media including raw data."""

    created_at: datetime
    updated_at: datetime
    raw_data: Optional[dict] = Field(None, description="Raw Instagram API response data")


class CarouselChild(BaseModel):
    """Schema for individual carousel child item from Instagram API."""

    id: str
    media_url: Optional[str] = None
    media_type: Optional[str] = None


class InstagramMediaAPIResponse(BaseModel):
    """Schema for Instagram Graph API media response."""

    model_config = ConfigDict(extra='allow')  # Allow extra fields from API

    id: str
    permalink: str
    caption: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    comments_count: Optional[int] = None
    like_count: Optional[int] = None
    shortcode: Optional[str] = None
    timestamp: Optional[str] = None
    is_comment_enabled: Optional[bool] = None
    is_processing_enabled: Optional[bool] = None
    username: Optional[str] = None
    owner: Optional[dict] = None
    children: Optional[dict] = None  # Contains {"data": [CarouselChild, ...]}


class MediaAnalysisResult(BaseModel):
    """Result of media analysis operation."""

    status: str = Field(..., description="Status: success, error, skipped")
    media_id: str
    reason: Optional[str] = Field(None, description="Reason for error or skip")
    media_context: Optional[str] = Field(None, description="Generated context")
    images_analyzed: Optional[int] = Field(None, description="Number of images analyzed")


class MediaCreateResult(BaseModel):
    """Result of media creation operation."""

    status: str = Field(..., description="Status: success, error, already_exists")
    media_id: str
    action: Optional[str] = Field(None, description="Action taken: created, already_exists")
    media: Optional[dict] = Field(None, description="Media details")
    reason: Optional[str] = Field(None, description="Reason for error")
