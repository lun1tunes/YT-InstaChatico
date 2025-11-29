"""Generate answer use case - handles question answering business logic."""

import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces.services import IAnswerService
from ..utils.decorators import handle_task_errors
from ..utils.time import now_db_utc
from ..models.question_answer import AnswerStatus
from ..interfaces.repositories import ICommentRepository, IAnswerRepository
from ..utils.comment_context import push_comment_context, reset_comment_context

logger = logging.getLogger(__name__)


class GenerateAnswerUseCase:
    """
    Use case for generating answers to question comments.

    Follows Dependency Inversion Principle - depends on IAnswerService protocol.
    """

    def __init__(
        self,
        session: AsyncSession,
        qa_service: IAnswerService,
        comment_repository_factory: Callable[..., ICommentRepository],
        answer_repository_factory: Callable[..., IAnswerRepository],
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            qa_service: Service implementing IAnswerService protocol
            comment_repository_factory: Factory producing CommentRepository instances
            answer_repository_factory: Factory producing AnswerRepository instances
        """
        self.session = session
        self.comment_repo: ICommentRepository = comment_repository_factory(session=session)
        self.answer_repo: IAnswerRepository = answer_repository_factory(session=session)
        self.qa_service = qa_service

    @handle_task_errors()
    async def execute(self, comment_id: str, retry_count: int = 0) -> Dict[str, Any]:
        """Execute answer generation use case."""
        logger.info(f"Starting answer generation | comment_id={comment_id} | retry_count={retry_count}")

        # 1. Get comment with classification
        comment = await self.comment_repo.get_with_classification(comment_id)
        if not comment:
            logger.error(f"Comment not found | comment_id={comment_id} | operation=generate_answer")
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        # 2. Get or create answer record
        answer_record = await self.answer_repo.get_by_comment_id(comment_id)
        if not answer_record:
            logger.info(f"Creating new answer record | comment_id={comment_id}")
            answer_record = await self.answer_repo.create_for_comment(comment_id)

        # 3. Update processing status (no commit yet)
        logger.debug(f"Marking answer as processing | comment_id={comment_id} | retry_count={retry_count}")
        answer_record.processing_status = AnswerStatus.PROCESSING
        answer_record.processing_started_at = now_db_utc()
        answer_record.retry_count = retry_count

        # 4. Generate answer using service
        context_token = push_comment_context(comment_id=comment_id, media_id=comment.media_id)
        try:
            answer_result = await self.qa_service.generate_answer(
                question_text=comment.text,
                conversation_id=comment.conversation_id,
                username=comment.username,
            )
        except Exception as exc:
            logger.error(
                f"Answer generation failed | comment_id={comment_id} | error={str(exc)} | "
                f"retry_count={retry_count}"
            )
            answer_record.processing_status = AnswerStatus.FAILED
            answer_record.last_error = str(exc)

            if retry_count < answer_record.max_retries:
                logger.info(
                    f"Scheduling retry | comment_id={comment_id} | retry_count={retry_count} | "
                    f"max_retries={answer_record.max_retries}"
                )
                result_payload = {"status": "retry", "reason": str(exc)}
            else:
                logger.warning(
                    f"Max retries exceeded | comment_id={comment_id} | retry_count={retry_count}"
                )
                result_payload = {"status": "error", "reason": str(exc)}

            try:
                await self.session.commit()
            except Exception as commit_exc:
                setattr(commit_exc, "should_reraise", True)
                await self.session.rollback()
                raise

            return result_payload

        finally:
            reset_comment_context(context_token)

        # 5. Update answer record with results
        answer_record.answer = answer_result.answer
        answer_record.answer_confidence = answer_result.answer_confidence
        answer_record.answer_quality_score = answer_result.answer_quality_score
        answer_record.llm_raw_response = getattr(answer_result, 'llm_raw_response', None)
        answer_record.input_tokens = answer_result.input_tokens
        answer_record.output_tokens = answer_result.output_tokens
        answer_record.processing_time_ms = answer_result.processing_time_ms
        answer_record.is_ai_generated = True
        answer_record.processing_status = AnswerStatus.COMPLETED
        answer_record.processing_completed_at = now_db_utc()

        try:
            await self.session.commit()
        except Exception as commit_exc:
            setattr(commit_exc, "should_reraise", True)
            await self.session.rollback()
            raise

        logger.info(
            f"Answer generation completed | comment_id={comment_id} | "
            f"confidence={answer_result.answer_confidence} | "
            f"quality_score={answer_result.answer_quality_score} | "
            f"input_tokens={answer_result.input_tokens} | "
            f"output_tokens={answer_result.output_tokens} | "
            f"processing_time_ms={answer_result.processing_time_ms}"
        )

        return {
            "status": "success",
            "answer": answer_result.answer,
            "confidence": answer_result.answer_confidence,
            "quality_score": answer_result.answer_quality_score,
        }
