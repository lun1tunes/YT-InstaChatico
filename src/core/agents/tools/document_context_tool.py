"""
Business documents context tool for answer agent.
Provides access to client business information (hours, location, promotions, policies).
IMPORTANT: This tool does NOT provide prices - prices come from embedding_search only.
"""

import logging
from agents import function_tool

from ...services.document_context_service import document_context_service
from ...models.db_helper import db_helper

logger = logging.getLogger(__name__)


async def _document_context_implementation() -> str:
    """
    Получить контекст бизнес-документов компании для ответов клиентам.

    Этот инструмент предоставляет информацию из загруженных документов компании (PDF, Excel и т.д.),
    преобразованных в формат Markdown для анализа AI-агентом.

    ⚠️ КРИТИЧЕСКИ ВАЖНО: Этот инструмент НЕ СОДЕРЖИТ информации о ценах!
    Цены ВСЕГДА берутся ТОЛЬКО из инструмента embedding_search (векторный поиск).

    ИСПОЛЬЗУЙ ЭТОТ ИНСТРУМЕНТ ДЛЯ:
    - Время работы и график компании
    - Адрес и местоположение
    - Текущие акции и специальные предложения
    - Политика компании (доставка, возврат, гарантия)
    - Контактная информация
    - Общее описание услуг и продуктов (БЕЗ ЦЕН)

    НЕ ИСПОЛЬЗУЙ для:
    - Вопросов о ценах (используй embedding_search)
    - Информации, которая может быстро устареть

    Returns:
        Отформатированный Markdown-контекст с бизнес-информацией из документов,
        или сообщение что документы отсутствуют.

    Examples:
        Правильное использование:
        - Клиент: "Какой у вас график работы?" → Вызови document_context() и найди режим работы
        - Клиент: "Где вы находитесь?" → Вызови document_context() и найди адрес
        - Клиент: "Какие сейчас акции?" → Вызови document_context() и найди акции

        Неправильное использование:
        - Клиент: "Сколько стоит услуга?" → ❌ НЕ используй document_context, используй embedding_search
    """
    try:
        logger.info("Document context tool called")

        # Create a new database session within the current event loop context
        # This prevents the "attached to a different loop" error
        from core.utils.task_helpers import get_db_session

        async with get_db_session() as session:
            # Get formatted context from service
            context = await document_context_service.get_client_context(session=session)

            if not context or context.strip() == "# Business Information" or context.strip() == "":
                logger.warning("No business documents available")
                return (
                    f"⚠️ NO BUSINESS DOCUMENTS AVAILABLE\n\n"
                    f"No business documents have been uploaded.\n"
                    f"Please inform the customer that specific business information "
                    f"(hours, location, policies) should be requested via direct contact.\n\n"
                    f"💡 Suggestion: Provide contact information (phone, email, DM) for detailed inquiries."
                )

            # Return the formatted markdown context
            formatted_output = f"✅ Business Documents Context:\n\n{context}\n\n"
            formatted_output += (
                f"💡 Usage: Use this information to answer questions about business hours, "
                f"location, promotions, and policies. DO NOT use prices from these documents - "
                f"always use embedding_search for price information."
            )

            logger.info(f"Document context retrieved | context_length={len(context)}")
            return formatted_output

    except Exception as e:
        error_msg = f"❌ Error retrieving business documents: {str(e)}"
        logger.error(f"Document context retrieval failed | error={str(e)}", exc_info=True)
        return error_msg


# Create the tool using @function_tool decorator
# This makes it available to OpenAI Agents SDK
document_context = function_tool(_document_context_implementation)
