"""Core Pydantic schemas for the application."""

from .classification import (
    ClassificationRequest,
    ClassificationResponse,
    ClassificationResultData,
)
from .answer import (
    AnswerRequest,
    AnswerResponse,
    AnswerResultData,
)
from .webhook import (
    WebhookProcessingResponse,
    TestCommentResponse,
)
from .comment import (
    # Base schemas
    CommentBase,
    HidingInfoBase,
    ClassificationInfoBase,
    AnswerInfoBase,
    ReplyInfoBase,
    TokenUsageBase,
    # Response schemas
    CommentDetailResponse,
    CommentWithClassificationResponse,
    CommentWithAnswerResponse,
    CommentFullResponse,
    # Request schemas
    HideCommentRequest,
    UnhideCommentRequest,
    SendReplyRequest,
    # Action response schemas
    HideCommentResponse,
    UnhideCommentResponse,
    SendReplyResponse,
    # List schemas
    CommentListItem,
    CommentListResponse,
)
from .media import (
    # Base schemas
    MediaBase,
    MediaResponse,
    MediaDetailResponse,
    # API schemas
    CarouselChild,
    InstagramMediaAPIResponse,
    # Result schemas
    MediaAnalysisResult,
    MediaCreateResult,
)

__all__ = [
    # Classification
    "ClassificationRequest",
    "ClassificationResponse",
    "ClassificationResultData",
    # Answer
    "AnswerRequest",
    "AnswerResponse",
    "AnswerResultData",
    # Webhook
    "WebhookProcessingResponse",
    "TestCommentResponse",
    # Comment - Base
    "CommentBase",
    "HidingInfoBase",
    "ClassificationInfoBase",
    "AnswerInfoBase",
    "ReplyInfoBase",
    "TokenUsageBase",
    # Comment - Response
    "CommentDetailResponse",
    "CommentWithClassificationResponse",
    "CommentWithAnswerResponse",
    "CommentFullResponse",
    # Comment - Request
    "HideCommentRequest",
    "UnhideCommentRequest",
    "SendReplyRequest",
    # Comment - Action Response
    "HideCommentResponse",
    "UnhideCommentResponse",
    "SendReplyResponse",
    # Comment - List
    "CommentListItem",
    "CommentListResponse",
    # Media - Base
    "MediaBase",
    "MediaResponse",
    "MediaDetailResponse",
    # Media - API
    "CarouselChild",
    "InstagramMediaAPIResponse",
    # Media - Result
    "MediaAnalysisResult",
    "MediaCreateResult",
]
