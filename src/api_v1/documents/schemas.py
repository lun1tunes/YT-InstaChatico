"""
Pydantic schemas for document API endpoints.
"""

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List
from uuid import UUID


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_name: str
    document_type: str
    s3_url: str
    processing_status: str
    created_at: datetime


class DocumentResponse(BaseModel):
    """Full document information."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    document_name: str
    document_type: str
    description: Optional[str] = None
    s3_url: str
    file_size_bytes: Optional[int] = None
    markdown_content: Optional[str] = None
    processing_status: str
    processing_error: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """List of documents."""

    total: int
    documents: List[DocumentResponse]


class DocumentSummaryResponse(BaseModel):
    """Document statistics summary."""

    total_documents: int
    completed: int
    failed: int
    pending: int
    types: List[str]
