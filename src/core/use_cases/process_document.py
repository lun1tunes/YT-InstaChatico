"""Process document use case - handles document processing business logic."""

import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces.services import IS3Service, IDocumentProcessingService
from ..interfaces.repositories import IDocumentRepository
from ..utils.decorators import handle_task_errors

logger = logging.getLogger(__name__)


class ProcessDocumentUseCase:
    """
    Use case for processing uploaded documents.

    Follows Dependency Inversion Principle - depends on service protocols.
    """

    def __init__(
        self,
        session: AsyncSession,
        s3_service: IS3Service,
        doc_processing_service: IDocumentProcessingService,
        document_repository_factory: Callable[..., IDocumentRepository],
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            s3_service: Service implementing IS3Service protocol
            doc_processing_service: Service implementing IDocumentProcessingService protocol
            document_repository_factory: Factory producing DocumentRepository instances
        """
        self.session = session
        self.document_repo: IDocumentRepository = document_repository_factory(session=session)
        self.s3_service = s3_service
        self.doc_processing = doc_processing_service

    @handle_task_errors()
    async def execute(self, document_id: str) -> Dict[str, Any]:
        """Execute document processing use case."""
        logger.info(f"Starting document processing | document_id={document_id}")

        # 1. Get document using repository
        document = await self.document_repo.get_by_id(document_id)

        if not document:
            logger.error(f"Document not found | document_id={document_id} | operation=process_document")
            return {"status": "error", "reason": f"Document {document_id} not found"}

        logger.info(
            f"Marking document as processing | document_id={document_id} | "
            f"document_name={document.document_name} | document_type={document.document_type}"
        )

        try:
            await self.document_repo.mark_processing(document)
            await self.session.flush()

            # 3. Download from S3
            logger.info(f"Downloading document from S3 | document_id={document_id} | s3_key={document.s3_key}")
            success, file_content, error = self.s3_service.download_file(document.s3_key)
            if not success:
                logger.error(
                    f"S3 download failed | document_id={document_id} | s3_key={document.s3_key} | error={error}"
                )
                raise Exception(f"Failed to download from S3: {error}")

            # 4. Process document
            logger.info(
                f"Processing document | document_id={document_id} | filename={document.document_name} | "
                f"type={document.document_type} | file_size={len(file_content)} bytes"
            )
            success, markdown, content_hash, error = self.doc_processing.process_document(
                file_content=file_content, filename=document.document_name, document_type=document.document_type
            )
            if not success:
                logger.error(
                    f"Document processing failed | document_id={document_id} | filename={document.document_name} | "
                    f"error={error}"
                )
                raise Exception(f"Failed to process document: {error}")

            # 5. Update document with results using repository method
            await self.document_repo.mark_completed(document, markdown)
            document.content_hash = content_hash
            try:
                await self.session.commit()
            except Exception as commit_exc:
                setattr(commit_exc, "should_reraise", True)
                await self.session.rollback()
                raise

            logger.info(
                f"Document processing completed | document_id={document_id} | "
                f"markdown_length={len(markdown)} | content_hash={content_hash}"
            )

            return {
                "status": "success",
                "document_id": document_id,
                "markdown_length": len(markdown),
            }

        except Exception as exc:
            logger.error(
                f"Document processing failed with exception | document_id={document_id} | "
                f"document_name={document.document_name} | error={str(exc)}"
            )
            # Update document with error using repository method
            await self.document_repo.mark_failed(document, str(exc))
            try:
                await self.session.commit()
            except Exception as commit_exc:
                setattr(commit_exc, "should_reraise", True)
                await self.session.rollback()
                raise
            raise exc
