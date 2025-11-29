"""Test comment processing use case - for development/testing mode."""

import logging
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.media import Media
from ..models.instagram_comment import InstagramComment
from ..models.comment_classification import CommentClassification, ProcessingStatus
from ..use_cases.classify_comment import ClassifyCommentUseCase
from ..use_cases.generate_answer import GenerateAnswerUseCase
from ..utils.time import now_db_utc
from ..interfaces.repositories import IMediaRepository, ICommentRepository

logger = logging.getLogger(__name__)


class TestCommentProcessingUseCase:
    """
    Process test comment through full pipeline (classification → answer generation).

    This is used in development mode to test the comment processing workflow
    without posting to Instagram.

    Note: This use case directly depends on other use cases rather than protocols,
    which is acceptable for testing/development utilities.
    """

    def __init__(
        self,
        session: AsyncSession,
        classify_use_case: Optional[ClassifyCommentUseCase] = None,
        answer_use_case: Optional[GenerateAnswerUseCase] = None,
        media_repository_factory: Callable[..., IMediaRepository] | None = None,
        comment_repository_factory: Callable[..., ICommentRepository] | None = None,
    ):
        """
        Initialize test use case with dependencies.

        Args:
            session: Database session
            classify_use_case: Optional ClassifyCommentUseCase (will use container if not provided)
            answer_use_case: Optional GenerateAnswerUseCase (will use container if not provided)
            media_repository_factory: Optional factory for MediaRepository instances
            comment_repository_factory: Optional factory for CommentRepository instances
        """
        self.session = session
        from ..repositories.media import MediaRepository
        from ..repositories.comment import CommentRepository

        media_repo_factory = media_repository_factory or MediaRepository
        comment_repo_factory = comment_repository_factory or CommentRepository
        self.media_repo: IMediaRepository = media_repo_factory(session=session)
        self.comment_repo: ICommentRepository = comment_repo_factory(session=session)
        self.classify_use_case = classify_use_case
        self.answer_use_case = answer_use_case

    async def execute(
        self,
        comment_id: str,
        media_id: str,
        user_id: str,
        username: str,
        text: str,
        parent_id: Optional[str] = None,
        media_caption: Optional[str] = None,
        media_url: Optional[str] = None,
    ) -> dict:
        """
        Process test comment through full pipeline.

        Returns:
            {
                "status": "success" | "error",
                "comment_id": str,
                "classification": str,
                "classification_reasoning": str,
                "answer": str | None,
                "processing_details": dict,
            }
        """
        logger.info(
            f"Starting test comment processing | comment_id={comment_id} | media_id={media_id} | "
            f"username={username} | has_parent={bool(parent_id)}"
        )

        try:
            # Step 1: Ensure media exists
            media = await self._ensure_test_media(media_id, media_caption, media_url)
            if not media:
                logger.error(f"Failed to create test media | media_id={media_id}")
                return {
                    "status": "error",
                    "comment_id": comment_id,
                    "reason": "Failed to create test media",
                }

            # Step 2: Create or update comment
            comment = await self._ensure_test_comment(
                comment_id, media_id, user_id, username, text, parent_id
            )

            # Step 3: Create classification record if needed
            await self._ensure_classification_record(comment_id)
            await self.session.commit()

            # Step 4: Run classification
            logger.info(f"Executing classification for test comment | comment_id={comment_id}")
            if not self.classify_use_case:
                # Use container if use case not provided (lazy import to avoid circular dependency)
                from ..container import get_container
                container = get_container()
                classification_use_case = container.classify_comment_use_case(session=self.session)
            else:
                classification_use_case = self.classify_use_case

            classification_result = await classification_use_case.execute(comment_id, retry_count=0)

            if classification_result.get("status") == "error":
                logger.error(
                    f"Test comment classification failed | comment_id={comment_id} | "
                    f"reason={classification_result.get('reason')}"
                )
                return {
                    "status": "error",
                    "comment_id": comment_id,
                    "reason": f"Classification failed: {classification_result.get('reason')}",
                }

            # Get classification details
            classification_type = classification_result.get("classification", "").lower()

            # Refresh comment to get classification reasoning
            await self.session.refresh(comment)
            reasoning = None
            if comment.classification:
                reasoning = comment.classification.reasoning

            logger.info(
                f"Test comment classified | comment_id={comment_id} | classification={classification_type}"
            )

            # Prepare result
            result = {
                "status": "success",
                "comment_id": comment_id,
                "classification": classification_result.get("classification"),
                "classification_reasoning": reasoning,
                "answer": None,
                "processing_details": {"classification_result": classification_result},
            }

            # Step 5: If question, generate answer
            if classification_type == "question / inquiry":
                logger.info(
                    f"Classification is question, generating answer | comment_id={comment_id} | "
                    f"classification={classification_type}"
                )
                if not self.answer_use_case:
                    # Use container if use case not provided (lazy import to avoid circular dependency)
                    from ..container import get_container
                    container = get_container()
                    answer_use_case = container.generate_answer_use_case(session=self.session)
                else:
                    answer_use_case = self.answer_use_case

                logger.info(f"Executing answer generation for test question | comment_id={comment_id}")
                answer_result = await answer_use_case.execute(comment_id, retry_count=0)

                if answer_result.get("status") == "error":
                    logger.warning(
                        f"Test answer generation failed | comment_id={comment_id} | "
                        f"reason={answer_result.get('reason')}"
                    )
                    result["processing_details"]["answer_error"] = answer_result.get("reason")
                else:
                    logger.info(
                        f"Test answer generated successfully | comment_id={comment_id} | "
                        f"confidence={answer_result.get('confidence')}"
                    )
                    result["answer"] = answer_result.get("answer")
                    result["processing_details"]["answer_result"] = answer_result

            logger.info(
                f"Test comment processing completed | comment_id={comment_id} | "
                f"classification={result.get('classification')} | has_answer={bool(result.get('answer'))}"
            )
            return result

        except Exception as e:
            await self.session.rollback()
            logger.exception(f"Error processing test comment {comment_id}")
            return {
                "status": "error",
                "comment_id": comment_id,
                "reason": f"Unexpected error: {str(e)}",
            }

    async def _ensure_test_media(
        self,
        media_id: str,
        media_caption: Optional[str],
        media_url: Optional[str],
    ) -> Optional[Media]:
        """Ensure test media exists in database."""
        media = await self.media_repo.get_by_id(media_id)

        if media:
            logger.debug(f"Test media {media_id} already exists")
            return media

        # Create test media
        now = now_db_utc()
        media = Media(
            id=media_id,
            permalink=f"https://instagram.com/p/test_{media_id}/",
            caption=media_caption or "Test media caption",
            media_url=media_url,
            media_type="IMAGE",
            username="test_user",
            created_at=now,
            updated_at=now,
        )

        self.session.add(media)
        await self.session.commit()
        logger.info(f"Created test media: {media_id}")

        return media

    async def _ensure_test_comment(
        self,
        comment_id: str,
        media_id: str,
        user_id: str,
        username: str,
        text: str,
        parent_id: Optional[str],
    ) -> InstagramComment:
        """Ensure test comment exists in database."""
        comment = await self.comment_repo.get_by_id(comment_id)

        if comment:
            logger.info(f"Test comment {comment_id} already exists, updating text")
            comment.text = text
            comment.parent_id = parent_id
            return comment

        # Create test comment
        now = now_db_utc()
        comment = InstagramComment(
            id=comment_id,
            media_id=media_id,
            user_id=user_id,
            username=username,
            text=text,
            parent_id=parent_id,
            created_at=now,
            raw_data={"test": True},
        )

        self.session.add(comment)
        logger.info(f"Created test comment: {comment_id}")

        return comment

    async def _ensure_classification_record(self, comment_id: str):
        """Ensure classification record exists for test comment."""
        comment = await self.comment_repo.get_by_id(comment_id)

        if not comment.classification:
            classification = CommentClassification(
                comment_id=comment_id,
                processing_status=ProcessingStatus.PENDING,
            )
            self.session.add(classification)
            logger.debug(f"Created classification record for test comment {comment_id}")
