from uuid import uuid4

import pytest
from httpx import AsyncClient

from core.config import settings
from core.models import Document
from core.utils.time import now_db_utc

from tests.integration.helpers import fetch_document


@pytest.mark.asyncio
async def test_register_document_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    s3_url = f"https://{settings.s3.s3_url}/{settings.s3.bucket_name}/docs/test.pdf"

    response = await client.post(
        "/api/v1/documents/register",
        data={"s3_url": s3_url, "document_name": "test.pdf", "description": "Test document"},
        headers=integration_environment["auth_headers"],
    )
    assert response.status_code == 200
    data = response.json()
    doc_id = data["id"]

    document = await fetch_document(session_factory, doc_id)
    assert document is not None
    assert document.processing_status == "pending"

    assert any(
        entry["task"] == "core.tasks.document_tasks.process_document_task" and entry["args"][0] == str(doc_id)
        for entry in task_queue.enqueued
    )


@pytest.mark.asyncio
async def test_register_document_invalid_url_format(integration_environment):
    client: AsyncClient = integration_environment["client"]
    s3_url = "https://invalid-provider.local/file.pdf"
    response = await client.post(
        "/api/v1/documents/register",
        data={"s3_url": s3_url, "document_name": "file.pdf"},
        headers=integration_environment["auth_headers"],
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_document_rejects_legacy_doc(integration_environment):
    client: AsyncClient = integration_environment["client"]
    s3_url = f"https://{settings.s3.s3_url}/{settings.s3.bucket_name}/docs/legacy.doc"

    response = await client.post(
        "/api/v1/documents/register",
        data={"s3_url": s3_url, "document_name": "legacy.doc"},
        headers=integration_environment["auth_headers"],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type. Supported: PDF, Excel, CSV, DOCX, TXT"


@pytest.mark.asyncio
async def test_upload_document_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("guide.pdf", b"pdf-bytes", "application/pdf")},
        data={"description": "Upload test"},
        headers=integration_environment["auth_headers"],
    )

    assert response.status_code == 200
    data = response.json()
    doc_id = data["id"]
    document = await fetch_document(session_factory, doc_id)
    assert document is not None
    assert document.processing_status == "pending"

    assert any(
        entry["task"] == "core.tasks.document_tasks.process_document_task" and entry["args"][0] == str(doc_id)
        for entry in task_queue.enqueued
    )


@pytest.mark.asyncio
async def test_upload_document_unsupported_type(integration_environment):
    client: AsyncClient = integration_environment["client"]
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("malware.exe", b"binary", "application/octet-stream")},
        headers=integration_environment["auth_headers"],
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_document_rejects_legacy_doc(integration_environment):
    client: AsyncClient = integration_environment["client"]
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("legacy.doc", b"legacy-bytes", "application/msword")},
        headers=integration_environment["auth_headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type. Supported: PDF, Excel, CSV, DOCX, TXT"


@pytest.mark.asyncio
async def test_list_documents_and_summary(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        doc = Document(
            document_name="ready.pdf",
            document_type="pdf",
            s3_bucket=settings.s3.bucket_name,
            s3_key="docs/ready.pdf",
            s3_url=f"https://{settings.s3.s3_url}/{settings.s3.bucket_name}/docs/ready.pdf",
            processing_status="completed",
            markdown_content="# Content",
            created_at=now_db_utc(),
        )
        session.add(doc)
        await session.commit()

    list_response = await client.get("/api/v1/documents", headers=integration_environment["auth_headers"])
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1

    summary_response = await client.get("/api/v1/documents/summary", headers=integration_environment["auth_headers"])
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_documents"] >= 1


@pytest.mark.asyncio
async def test_get_document_not_found(integration_environment):
    client: AsyncClient = integration_environment["client"]
    missing_id = uuid4()
    response = await client.get(f"/api/v1/documents/{missing_id}", headers=integration_environment["auth_headers"])
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reprocess_document(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    async with session_factory() as session:
        doc = Document(
            document_name="fail.pdf",
            document_type="pdf",
            s3_bucket=settings.s3.bucket_name,
            s3_key="docs/fail.pdf",
            s3_url=f"https://{settings.s3.s3_url}/{settings.s3.bucket_name}/docs/fail.pdf",
            processing_status="failed",
            processing_error="error",
            created_at=now_db_utc(),
        )
        session.add(doc)
        await session.commit()
        doc_id = doc.id

    response = await client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=integration_environment["auth_headers"])
    assert response.status_code == 200
    assert any(
        entry["task"] == "core.tasks.document_tasks.process_document_task" and entry["args"][0] == str(doc_id)
        for entry in task_queue.enqueued
    )
