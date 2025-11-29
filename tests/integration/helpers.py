from typing import Optional
from uuid import UUID

from sqlalchemy import select

from core.models import CommentClassification, Document, InstagramComment


async def fetch_comment(session_factory, comment_id: str) -> Optional[InstagramComment]:
    async with session_factory() as session:
        return await session.get(InstagramComment, comment_id)


async def fetch_classification(session_factory, comment_id: str) -> Optional[CommentClassification]:
    async with session_factory() as session:
        return await session.scalar(
            select(CommentClassification).where(CommentClassification.comment_id == comment_id)
        )


async def fetch_document(session_factory, document_id) -> Optional[Document]:
    async with session_factory() as session:
        doc_id = document_id
        if isinstance(doc_id, str):
            doc_id = UUID(doc_id)
        return await session.get(Document, doc_id)
