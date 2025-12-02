"""
Service protocols for dependency injection.

These protocols define the interfaces that services must implement,
allowing use cases to depend on abstractions rather than concrete implementations.
This follows the Dependency Inversion Principle (DIP) from SOLID.
"""

from typing import Any, Dict, List, Optional, Protocol, BinaryIO, AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.classification import ClassificationResponse
from ..schemas.answer import AnswerResponse
from ..models import Media


class IClassificationService(Protocol):
    """Protocol for comment classification services."""

    async def classify_comment(
        self,
        comment_text: str,
        conversation_id: Optional[str] = None,
        media_context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResponse:
        """
        Classify a comment into predefined categories.

        Args:
            comment_text: The text of the comment to classify
            conversation_id: Optional conversation ID for session management
            media_context: Optional context about the media post

        Returns:
            ClassificationResponse with classification result
        """
        ...

    def generate_conversation_id(
        self,
        comment_id: str,
        parent_id: Optional[str] = None,
    ) -> str:
        """
        Generate stable conversation identifier for a comment thread.

        Args:
            comment_id: Identifier of the current comment
            parent_id: Optional identifier of the parent comment

        Returns:
            Deterministic conversation ID string
        """
        ...


class IAnswerService(Protocol):
    """Protocol for answer generation services."""

    async def generate_answer(
        self,
        question_text: str,
        conversation_id: Optional[str] = None,
        media_context: Optional[Dict[str, Any]] = None,
        username: Optional[str] = None,
    ) -> AnswerResponse:
        """
        Generate an answer to a customer question.

        Args:
            question_text: The question text to answer
            conversation_id: Optional conversation ID for context
            media_context: Optional media post context
            username: Optional username of the person asking

        Returns:
            AnswerResponse with generated answer
        """
        ...


class IInstagramService(Protocol):
    """Protocol for Instagram API operations."""

    async def send_reply_to_comment(
        self, comment_id: str, message: str
    ) -> Dict[str, Any]:
        """
        Send a reply to an Instagram comment.

        Args:
            comment_id: ID of the comment to reply to
            message: Reply message text

        Returns:
            Dict with success status and response data
        """
        ...

    async def hide_comment(self, comment_id: str, hide: bool = True) -> Dict[str, Any]:
        """
        Hide or unhide an Instagram comment.

        Args:
            comment_id: ID of the comment to hide/unhide
            hide: True to hide, False to unhide

        Returns:
            Dict with success status and response data
        """
        ...

    async def delete_comment(self, comment_id: str) -> Dict[str, Any]:
        """
        Permanently delete an Instagram comment.

        Args:
            comment_id: ID of the comment to delete
        """
        ...

    async def get_comment_info(self, comment_id: str) -> Dict[str, Any]:
        """
        Get information about an Instagram comment.

        Args:
            comment_id: ID of the comment

        Returns:
            Dict with comment information
        """
        ...

    async def get_media_info(self, media_id: str) -> Dict[str, Any]:
        """
        Get information about an Instagram media post.

        Args:
            media_id: ID of the media post

        Returns:
            Dict with media information
        """
        ...

    async def delete_comment_reply(self, reply_id: str) -> Dict[str, Any]:
        """
        Delete an Instagram reply/comment by ID.

        Args:
            reply_id: ID of the reply to delete
        """
        ...

    async def set_media_comment_status(self, media_id: str, enabled: bool) -> Dict[str, Any]:
        """
        Enable or disable comments on an Instagram media post.

        Args:
            media_id: ID of the media post
            enabled: True to enable comments, False to disable

        Returns:
            Dict with success status and response data
        """
        ...

    async def validate_token(self) -> Dict[str, Any]:
        """
        Validate the Instagram access token.

        Returns:
            Dict with validation result
        """
        ...

    async def get_page_info(self) -> Dict[str, Any]:
        """
        Get Instagram page information.

        Returns:
            Dict with page information
        """
        ...


class IMediaService(Protocol):
    """Protocol for media management services."""

    async def get_or_create_media(
        self, media_id: str, session: AsyncSession
    ) -> Optional[Media]:
        """
        Get media from database or create from Instagram API.

        Args:
            media_id: Instagram media ID
            session: Database session

        Returns:
            Media model instance or None if failed
        """
        ...

    async def set_comment_status(
        self,
        media_id: str,
        enabled: bool,
        session: AsyncSession,
    ) -> Dict[str, Any]:
        """Enable or disable comments for a media record and persist change."""
        ...

    async def refresh_media_urls(
        self,
        media_id: str,
        session: AsyncSession,
    ) -> Optional[Media]:
        """
        Refresh media URLs by fetching latest data from Instagram.

        Returns:
            Updated media record or None if refresh failed
        """
        ...


class IYouTubeService(Protocol):
    """Protocol for YouTube Data API interactions (comments/videos)."""

    async def list_channel_videos(
        self,
        channel_id: Optional[str] = None,
        page_token: Optional[str] = None,
        max_results: int = 50,
    ) -> dict:
        """List videos for a channel (used for polling new content)."""
        ...

    async def list_comment_threads(
        self,
        video_id: str,
        page_token: Optional[str] = None,
        max_results: int = 50,
        order: str = "time",
    ) -> dict:
        """Fetch top-level comment threads for a video (includes replies if available)."""
        ...

    async def list_comment_replies(
        self,
        parent_id: str,
        page_token: Optional[str] = None,
        max_results: int = 100,
        order: str = "time",
    ) -> dict:
        """Fetch replies for a specific top-level comment (comments.list with parentId)."""
        ...

    async def reply_to_comment(self, parent_id: str, text: str) -> dict:
        """Post a reply to an existing comment."""
        ...

    async def delete_comment(self, comment_id: str) -> None:
        """Delete a comment."""
        ...

    async def get_video_details(self, video_id: str) -> dict:
        """Fetch video metadata/context (title, description, thumbnails, stats)."""
        ...


class IMediaAnalysisService(Protocol):
    """Protocol for media analysis services (AI vision)."""

    async def analyze_media_image(
        self, media_url: str, caption: Optional[str] = None
    ) -> Optional[str]:
        """
        Analyze a single media image using AI.

        Args:
            media_url: URL of the image to analyze
            caption: Optional caption for additional context

        Returns:
            Analysis description or None if failed
        """
        ...

    async def analyze_carousel_images(
        self, media_urls: List[str], caption: Optional[str] = None
    ) -> Optional[str]:
        """
        Analyze multiple images from a carousel post.

        Args:
            media_urls: List of image URLs to analyze
            caption: Optional caption for additional context

        Returns:
            Combined analysis description or None if failed
        """
        ...


class IEmbeddingService(Protocol):
    """Protocol for embedding and semantic search services."""

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text.

        Args:
            text: Text to embed

        Returns:
            List of float values representing the embedding
        """
        ...

    async def search_similar_products(
        self, query_text: str, session: AsyncSession, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Search for similar products using semantic search.

        Args:
            query_text: Query text to search for
            session: Database session
            top_k: Number of results to return

        Returns:
            List of similar products with similarity scores
        """
        ...

    async def add_product(
        self,
        title: str,
        description: str,
        category: str,
        session: AsyncSession,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a product to the embedding database.

        Args:
            title: Product title
            description: Product description
            category: Product category
            session: Database session
            metadata: Optional metadata

        Returns:
            Dict with product info and embedding ID
        """
        ...


class ITelegramService(Protocol):
    """Protocol for Telegram notification services."""

    async def send_notification(
        self, comment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send notification to Telegram (generic method).

        Args:
            comment_data: Dictionary containing comment information

        Returns:
            Dict with success status and response details
        """
        ...

    async def send_urgent_issue_notification(
        self, comment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send urgent issue notification to Telegram.

        Args:
            comment_data: Dictionary containing comment information

        Returns:
            Dict with success status and response details
        """
        ...

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test Telegram bot connection.

        Returns:
            Dict with connection test results
        """
        ...


class IS3Service(Protocol):
    """Protocol for S3 storage services."""

    def get_bucket_name(self) -> str:
        """Return configured bucket name."""
        ...

    def download_file(self, s3_key: str) -> tuple[bool, Optional[bytes], Optional[str]]:
        """
        Download file from S3.

        Args:
            s3_key: S3 key/path of the file

        Returns:
            Tuple of (success: bool, content: bytes or None, error: str or None)
        """
        ...

    def upload_file(
        self, file_obj: BinaryIO, s3_key: str, content_type: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Upload file to S3.

        Args:
            file_obj: File-like object to upload
            s3_key: S3 key/path for the file
            content_type: Optional content type

        Returns:
            Tuple of (success: bool, error: str or None)
        """
        ...

    def generate_upload_key(self, filename: str, client_id: Optional[str] = None) -> str:
        """
        Generate key for uploading new document.

        Args:
            filename: Original filename
            client_id: Optional client identifier for multi-tenant scenarios
        """
        ...


class IDocumentProcessingService(Protocol):
    """Protocol for document processing services."""

    def process_document(
        self, file_content: bytes, filename: str, document_type: str
    ) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Process document and extract content as markdown.

        Args:
            file_content: File content as bytes
            filename: Name of the file
            document_type: Type of document (pdf, docx, etc.)

        Returns:
            Tuple of (success: bool, markdown: str or None, content_hash: str or None, error: str or None)
        """
        ...


class MediaImageFetchResult(Protocol):
    status: int
    content_type: Optional[str]
    cache_control: Optional[str]

    def iter_bytes(self) -> AsyncIterator[bytes]:
        ...

    async def close(self) -> None:
        ...


class IMediaProxyService(Protocol):
    """Protocol for media proxy fetch service."""

    async def fetch_image(self, url: str) -> MediaImageFetchResult:
        ...

    def detect_document_type(self, filename: str) -> str:
        """
        Detect document type from filename.

        Args:
            filename: Name of the file

        Returns:
            Document type string
        """
        ...


class IDocumentContextService(Protocol):
    """Protocol for retrieving and formatting document context."""

    async def get_client_context(self, session: AsyncSession) -> str:
        """Return formatted markdown context for all documents."""
        ...

    async def get_document_summary(self, session: AsyncSession) -> dict:
        """Return summary statistics across documents."""
        ...


class ITaskQueue(Protocol):
    """Protocol for task queue abstraction (decouples from Celery)."""

    def enqueue(
        self,
        task_name: str,
        *args,
        countdown: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        Enqueue a task for background processing.

        Args:
            task_name: Name of the task to execute
            *args: Positional arguments for the task
            countdown: Optional delay in seconds before execution
            **kwargs: Keyword arguments for the task

        Returns:
            Task ID or reference
        """
        ...

    def enqueue_batch(
        self, tasks: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Enqueue multiple tasks at once.

        Args:
            tasks: List of task dictionaries with name and args

        Returns:
            List of task IDs
        """
        ...
