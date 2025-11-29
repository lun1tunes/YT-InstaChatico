"""
Document Context Service

Retrieves and formats document content for AI agent context.
"""

import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.repositories.document import DocumentRepository

logger = logging.getLogger(__name__)


class DocumentContextService:
    """Service for retrieving document context for AI agents."""

    async def get_client_context(self, session: AsyncSession) -> str:
        """
        Get formatted markdown context from all documents.

        Args:
            session: Database session

        Returns:
            Formatted markdown string with all document content
        """
        try:
            # Use repository for data access
            document_repo = DocumentRepository(session)

            # Fetch all completed documents
            documents = await document_repo.get_completed_with_content()

            if not documents:
                logger.info("No documents found")
                return ""

            # Format documents into context
            context_parts = ["# Business Information\n"]

            for doc in documents:
                context_parts.append(f"\n## {doc.document_name}\n")
                if doc.description:
                    context_parts.append(f"*{doc.description}*\n")
                context_parts.append(f"\n{doc.markdown_content}\n")
                context_parts.append("\n---\n")

            context = "\n".join(context_parts)
            logger.info(f"Retrieved context: {len(context)} characters from {len(documents)} documents")

            return context

        except Exception as e:
            logger.error(f"Error retrieving document context: {e}", exc_info=True)
            return ""

    async def get_document_summary(self, session: AsyncSession) -> dict:
        """
        Get summary statistics about documents.

        Args:
            session: Database session

        Returns:
            Dict with document statistics
        """
        try:
            # Use repository for data access
            document_repo = DocumentRepository(session)
            return await document_repo.get_summary_stats()

        except Exception as e:
            logger.error(f"Error getting document summary: {e}")
            return {"error": str(e)}

    async def format_context_for_agent(self, session: AsyncSession) -> str:
        """
        Format document context for AI agent (alias for get_client_context).

        Args:
            session: Database session

        Returns:
            Formatted markdown context for agent
        """
        return await self.get_client_context(session)


# Singleton instance
document_context_service = DocumentContextService()
