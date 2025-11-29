"""Pydantic schemas for Instagram webhook validation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WebhookVerification(BaseModel):
    """Webhook verification challenge from Instagram."""

    hub_mode: Literal["subscribe"] = Field(..., description="Must be 'subscribe' for verification")
    hub_challenge: str = Field(..., min_length=1, description="Challenge string to echo back")
    hub_verify_token: str = Field(..., min_length=1, description="Verification token")


class CommentAuthor(BaseModel):
    """Instagram user who created the comment."""

    id: str = Field(..., min_length=1, description="Instagram user ID")
    username: str = Field(..., min_length=1, max_length=30, description="Instagram username")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Ensure username doesn't contain invalid characters."""
        if not v.replace(".", "").replace("_", "").isalnum():
            raise ValueError("Username contains invalid characters")
        return v.lower()


class CommentMedia(BaseModel):
    """Instagram media (post) associated with the comment."""

    id: str = Field(..., min_length=1, description="Instagram media ID")
    media_product_type: str | None = Field(None, description="Media product type (e.g., 'FEED', 'REELS')")


class CommentValue(BaseModel):
    """Comment data from Instagram webhook."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    from_: CommentAuthor = Field(..., alias="from", description="Comment author")
    media: CommentMedia = Field(..., description="Associated media")
    id: str = Field(..., min_length=1, description="Comment ID")
    parent_id: str | None = Field(None, description="Parent comment ID for replies")
    text: str = Field(..., min_length=1, max_length=2200, description="Comment text")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Ensure text is not empty after stripping."""
        if not v.strip():
            raise ValueError("Comment text cannot be empty")
        return v

    def is_reply(self) -> bool:
        """Check if this comment is a reply to another comment."""
        return self.parent_id is not None

    def is_from_user(self, username: str) -> bool:
        """Check if comment is from a specific user."""
        return self.from_.username.lower() == username.lower()


class CommentChange(BaseModel):
    """Change notification from Instagram webhook."""

    field: Literal["comments"] = Field(..., description="Field that changed (must be 'comments')")
    value: CommentValue = Field(..., description="Comment data")


class WebhookEntry(BaseModel):
    """Entry in Instagram webhook payload."""

    id: str = Field(..., min_length=1, description="Instagram business account ID")
    time: int = Field(..., gt=0, description="Unix timestamp of the event")
    changes: list[CommentChange] = Field(..., min_length=1, description="List of changes")

    @field_validator("time")
    @classmethod
    def validate_timestamp(cls, v: int) -> int:
        """Ensure timestamp is reasonable (not too old, not in future)."""
        now = int(datetime.utcnow().timestamp())
        if v > now + 3600:  # Not more than 1 hour in future
            raise ValueError("Timestamp is too far in the future")
        if v < now - 86400 * 7:  # Not older than 7 days
            raise ValueError("Timestamp is too old")
        return v

    def get_timestamp(self) -> datetime:
        """Convert Unix timestamp to datetime object."""
        return datetime.fromtimestamp(self.time)


class WebhookPayload(BaseModel):
    """Instagram webhook payload."""

    model_config = ConfigDict(str_strip_whitespace=True)

    entry: list[WebhookEntry] = Field(..., min_length=1, description="List of entries")
    object: Literal["instagram"] = Field(..., description="Object type (must be 'instagram')")

    def get_all_comments(self) -> list[tuple[WebhookEntry, CommentValue]]:
        """Extract all comments from the payload with their entry context."""
        comments = []
        for entry in self.entry:
            for change in entry.changes:
                if change.field == "comments":
                    comments.append((entry, change.value))
        return comments


class TestCommentPayload(BaseModel):
    """Simplified test payload for development/testing mode."""

    model_config = ConfigDict(str_strip_whitespace=True)

    comment_id: str = Field(..., min_length=1, description="Test comment ID (can be any unique string)")
    media_id: str = Field(..., min_length=1, description="Test media ID")
    user_id: str = Field(..., min_length=1, description="Test user ID")
    username: str = Field(..., min_length=1, description="Test username")
    text: str = Field(..., min_length=1, max_length=2200, description="Comment text")
    parent_id: str | None = Field(None, description="Parent comment ID for testing replies")
    media_caption: str | None = Field(None, description="Optional media caption for context")
    media_url: str | None = Field(None, description="Optional media URL")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Ensure text is not empty after stripping."""
        if not v.strip():
            raise ValueError("Comment text cannot be empty")
        return v
