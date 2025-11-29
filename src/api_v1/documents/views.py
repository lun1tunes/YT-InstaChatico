"""
Document Management API Endpoints
"""

import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.db_helper import db_helper
from core.models.document import Document
from core.config import settings
from core.interfaces.services import (
    IS3Service,
    IDocumentProcessingService,
    ITaskQueue,
    IDocumentContextService,
)
from core.dependencies import (
    get_s3_service,
    get_document_processing_service,
    get_task_queue,
    get_document_context_service,
)
from api_v1.comments.views import require_service_token
from .schemas import DocumentUploadResponse, DocumentResponse, DocumentListResponse, DocumentSummaryResponse

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(require_service_token)],
)


async def _create_document_record(
    session: AsyncSession,
    *,
    document_name: str,
    document_type: str,
    description: Optional[str],
    s3_bucket: str,
    s3_key: str,
    s3_url: str,
    file_size_bytes: int,
    task_queue: ITaskQueue,
) -> Document:
    """Persist document metadata and enqueue background processing task."""

    document = Document(
        document_name=document_name,
        document_type=document_type,
        description=description,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        s3_url=s3_url,
        file_size_bytes=file_size_bytes,
        processing_status="pending",
    )

    session.add(document)
    await session.commit()
    await session.refresh(document)

    task_queue.enqueue(
        "core.tasks.document_tasks.process_document_task",
        str(document.id),
    )

    return document


@router.post("/register", response_model=DocumentUploadResponse)
async def register_document(
    s3_url: str = Form(...),
    document_name: str = Form(...),
    description: Optional[str] = Form(None),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    s3_service: IS3Service = Depends(get_s3_service),
    document_processing_service: IDocumentProcessingService = Depends(get_document_processing_service),
    task_queue: ITaskQueue = Depends(get_task_queue),
):
    """
    Register a document that's already in S3 (uploaded by main app).

    This endpoint is for when your main app has already uploaded the file to S3.
    Just provide the S3 URL and metadata - this app will download, process to markdown,
    and use in answer logic.

    Flow:
    1. Main app uploads file to S3
    2. Main app calls this endpoint with S3 URL + metadata
    3. This app downloads from S3, processes with pdfplumber to markdown
    4. Markdown stored in DB and used by answer agent
    """
    try:
        # Extract S3 key from URL
        # Supported formats:
        # 1. S3 URI: s3://bucket/path/to/file.pdf
        # 2. HTTPS URL: https://s3.region.storage.selcloud.ru/bucket/path/to/file.pdf
        # 3. HTTPS URL: https://bucket.s3.region.storage.selcloud.ru/path/to/file.pdf
        s3_key = None

        bucket_name = s3_service.get_bucket_name()
        logger.info(f"Processing S3 URL: {s3_url}")
        logger.info(f"Expected bucket: {bucket_name}")

        if s3_url.startswith("s3://"):
            # S3 URI format: s3://bucket/path/to/file.pdf
            uri_path = s3_url.replace("s3://", "")
            parts = uri_path.split("/", 1)
            logger.info(f"S3 URI parts: bucket='{parts[0]}', path='{parts[1] if len(parts) > 1 else 'NONE'}'")

            if len(parts) > 1:
                bucket_from_uri = parts[0]
                if bucket_from_uri == bucket_name:
                    s3_key = parts[1]
                    logger.info(f"Extracted S3 key from URI: {s3_key}")
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Bucket mismatch. URI has '{bucket_from_uri}' but expected '{s3_service.bucket_name}'",
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid S3 URI format. Must be: s3://{s3_service.bucket_name}/path/to/file",
                )
        elif settings.s3.s3_url in s3_url:
            # Format: https://s3.ru-7.storage.selcloud.ru/bucket/path/to/file.pdf
            parts = s3_url.split(f"{settings.s3.s3_url}/")
            if len(parts) > 1:
                # Remove bucket name from path
                path = parts[1]
                if path.startswith(f"{bucket_name}/"):
                    s3_key = path.replace(f"{bucket_name}/", "", 1)
                else:
                    s3_key = path
                logger.info(f"Extracted S3 key from HTTPS URL: {s3_key}")
        elif bucket_name in s3_url:
            # Format: https://bucket.s3.ru-7.storage.selcloud.ru/path/to/file.pdf
            parts = s3_url.split(f"{bucket_name}.", 1)
            if len(parts) > 1:
                s3_key = parts[1].split("/", 1)[1] if "/" in parts[1] else None
                logger.info(f"Extracted S3 key from bucket subdomain URL: {s3_key}")

        if not s3_key:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot extract S3 key from URL. Supported formats: s3://{bucket_name}/path/to/file OR https://{settings.s3.s3_url}/{bucket_name}/path/to/file",
            )

        # Detect document type from filename
        document_type = document_processing_service.detect_document_type(document_name)

        if document_type == "other":
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Supported: PDF, Excel, CSV, DOCX, TXT",
            )

        # Verify file exists in S3
        success, file_content, error = s3_service.download_file(s3_key)
        if not success:
            raise HTTPException(status_code=404, detail=f"File not found in S3: {error}")

        file_size = len(file_content) if file_content else 0

        document = await _create_document_record(
            session,
            document_name=document_name,
            document_type=document_type,
            description=description,
            s3_bucket=bucket_name,
            s3_key=s3_key,
            s3_url=s3_url,
            file_size_bytes=file_size,
            task_queue=task_queue,
        )

        logger.info(f"Document registered from S3: {document.id} - {document_name} - {s3_url}")

        return DocumentUploadResponse.model_validate(document)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    s3_service: IS3Service = Depends(get_s3_service),
    document_processing_service: IDocumentProcessingService = Depends(get_document_processing_service),
    task_queue: ITaskQueue = Depends(get_task_queue),
):
    """
    Upload a document directly to this app (alternative to /register).

    This endpoint handles the full upload: receives file, uploads to S3, processes to markdown.
    Use /register endpoint if file is already in S3.

    Supports: PDF, Excel, CSV, DOCX, TXT files
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        # Detect document type
        document_type = document_processing_service.detect_document_type(file.filename)

        if document_type == "other":
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Supported: PDF, Excel, CSV, DOCX, TXT",
            )

        # Check file size
        file_content = await file.read()
        file_size = len(file_content)
        max_size = 50 * 1024 * 1024  # 50MB

        if file_size > max_size:
            raise HTTPException(status_code=413, detail=f"File too large. Maximum size: {max_size / 1024 / 1024}MB")

        # Generate S3 key
        s3_key = s3_service.generate_upload_key(file.filename)

        # Upload to S3
        from io import BytesIO

        success, s3_url_or_error = s3_service.upload_file(BytesIO(file_content), s3_key, content_type=file.content_type)

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {s3_url_or_error}")

        document = await _create_document_record(
            session,
            document_name=file.filename,
            document_type=document_type,
            description=description,
            s3_bucket=s3_service.get_bucket_name(),
            s3_key=s3_key,
            s3_url=s3_url_or_error,
            file_size_bytes=file_size,
            task_queue=task_queue,
        )

        logger.info(f"Document uploaded: {document.id} - {file.filename}")

        return DocumentUploadResponse.model_validate(document)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    """List documents with optional filters."""
    try:
        # Build query
        stmt = select(Document)

        if status:
            stmt = stmt.where(Document.processing_status == status)

        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar()

        # Get documents
        stmt = stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        documents = result.scalars().all()

        return DocumentListResponse(total=total, documents=[DocumentResponse.model_validate(doc) for doc in documents])

    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=DocumentSummaryResponse)
async def get_documents_summary(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    document_context_service: IDocumentContextService = Depends(get_document_context_service),
):
    """Get summary statistics for documents."""
    try:
        summary = await document_context_service.get_document_summary(session)
        return DocumentSummaryResponse(**summary)
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: UUID, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
    """Get a specific document by ID."""
    try:
        stmt = select(Document).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        return DocumentResponse.model_validate(document)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    s3_service: IS3Service = Depends(get_s3_service),
):
    """Delete a document (from DB and S3)."""
    try:
        # Get document
        stmt = select(Document).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete from S3
        success, error = s3_service.delete_file(document.s3_key)
        if not success:
            logger.warning(f"Failed to delete from S3: {error}")

        # Delete from database
        await session.delete(document)
        await session.commit()

        logger.info(f"Document deleted: {document_id}")
        return {"message": "Document deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: UUID,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    task_queue: ITaskQueue = Depends(get_task_queue),
):
    """Reprocess a failed document."""
    try:
        # Get document
        stmt = select(Document).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Reset status
        document.processing_status = "pending"
        document.processing_error = None
        await session.commit()

        # Queue for reprocessing
        task_queue.enqueue(
            "core.tasks.document_tasks.process_document_task",
            str(document_id),
        )

        return {"message": "Document queued for reprocessing"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reprocessing document: {e}")
        raise HTTPException(status_code=500, detail=str(e))
