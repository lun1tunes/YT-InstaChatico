"""
Semantic search tool for products/services using vector embeddings.
Automatically filters out-of-distribution results below 70% similarity threshold.
"""

import logging
from typing import Optional
from agents import function_tool

from ...services.embedding_service import EmbeddingService
from ...models.db_helper import db_helper
from ...utils.comment_context import get_comment_context

logger = logging.getLogger(__name__)


async def _embedding_search_implementation(
    query: str,
    limit: int = 5,
    category: Optional[str] = None,
    comment_id: Optional[str] = None,
) -> str:
    """
    Поиск продуктов и услуг по семантическому сходству с автоматической фильтрацией нерелевантных результатов.

    Этот инструмент преобразует запросы на естественном языке в векторные представления и выполняет
    поиск по базе данных с использованием косинусного сходства. АВТОМАТИЧЕСКИ ФИЛЬТРУЕТ результаты
    с уровнем сходства ниже порога (out-of-distribution detection), чтобы не возвращать нерелевантные продукты.

    ⚠️ ВАЖНО: ОБОГАЩАЙ ЗАПРОС МЕДИА-КОНТЕКСТОМ!
    - Перед вызовом ВСЕГДА проверяй медиа-контекст (подпись поста, описание)
    - Если в контексте упоминается конкретный продукт → используй его ПОЛНОЕ название в query
    - Пример: Клиент: "Цена скраба?", Контекст: "Кофейный скраб антицеллюлитный"
      → query должен быть "кофейный скраб антицеллюлитный", НЕ просто "скраб"

    ИСПОЛЬЗУЙ ЭТОТ ИНСТРУМЕНТ КОГДА:
    - Клиент спрашивает о конкретных продуктах или услугах ("Есть ли у вас квартиры?")
    - Клиент хочет узнать цены или наличие ("Сколько стоит консультация?")
    - Клиент ищет по характеристикам ("квартиры в центре", "премиум услуги")

    НЕ ИСПОЛЬЗУЙ для:
    - Общих вопросов о режиме работы, контактной информации или местоположении
    - Вопросов, не связанных с конкретными продуктами/услугами

    ВАЖНО: Если инструмент вернул "NO RELEVANT PRODUCTS FOUND", это означает, что запрошенный
    продукт/услуга НЕ ПРЕДСТАВЛЕНЫ в каталоге. Вежливо сообщи клиенту, что это недоступно.

    Args:
        query: Поисковый запрос на естественном языке на любом языке (например, "квартиры в центре",
               "apartments", "премиум консультация"). Будь конкретен для лучших результатов.
        limit: Максимальное количество высокоуверенных результатов для возврата. По умолчанию 5, максимум 10.
               Возвращаются только результаты с уровнем сходства выше порога релевантности.
        category: Необязательный фильтр для поиска только в определенной категории (например, "Недвижимость",
                 "Услуги"). Используй это для сужения поиска, когда знаешь категорию.

    Returns:
        Отформатированная строка с одним из трех исходов:
        1. HIGH-CONFIDENCE RESULTS: Список продуктов с названиями, описаниями, ценами
           и уровнем уверенности. Ты можешь безопасно использовать эту информацию.
        2. NO RELEVANT PRODUCTS FOUND: Все результаты отфильтрованы как нерелевантные (out-of-distribution).
           Запрошенный продукт/услуга недоступны. Вежливо сообщи об этом клиенту.
        3. DATABASE EMPTY: В базе данных пока нет продуктов. Предложи альтернативный способ связи.

    Examples:
        Правильное использование:
        - query: "квартиры в центре" → Вернет квартиры с релевантными результатами
        - query: "кофейный скраб антицеллюлитный" → Вернет точный продукт
        - query: "недвижимость", category: "Недвижимость" → Только недвижимость

        С использованием медиа-контекста:
        - Контекст: "Кофейный скраб", Клиент: "Цена?" → query: "кофейный скраб" ✅
        - Контекст: "Сыворотка с витамином С", Клиент: "Сколько стоит?" → query: "сыворотка витамин C" ✅

        Примеры OOD (не найдено):
        - query: "пицца" → Вернет NO RELEVANT PRODUCTS FOUND (мы не продаем пиццу)
        - query: "автомобили" → Вернет NO RELEVANT PRODUCTS FOUND (нет в нашем каталоге)
    """
    try:
        # Limit validation
        limit = min(max(1, limit), 10)

        logger.info(
            f"Embedding search started | query='{query}' | limit={limit} | "
            f"category={'all' if not category else category}"
        )

        # Create a new database session within the current event loop context
        # This prevents the "attached to a different loop" error
        from core.utils.task_helpers import get_db_session

        async with get_db_session() as session:
            try:
                # Initialize embedding service with proper cleanup
                async with EmbeddingService() as embedding_service:
                    ctx = get_comment_context()
                    comment_ref = comment_id or ctx.get("comment_id")
                    # Perform semantic search (get more results to account for filtering)
                    all_results = await embedding_service.search_similar_products(
                        query=query,
                        session=session,
                        limit=limit * 2,  # Get more results to filter
                        category_filter=category,
                        include_inactive=False,
                        comment_id=comment_ref,
                    )

                    # Handle empty database
                    if not all_results:
                        logger.warning("Embedding search: database empty")
                        return (
                            f"⚠️ DATABASE EMPTY\n\n"
                            f"No products/services are currently in the database.\n"
                            f"Please add products using the populate_embeddings.py script."
                        )

                    # CRITICAL: Filter out OOD results (similarity < threshold)
                    high_confidence_results = [r for r in all_results if not r["is_ood"]]
                    low_confidence_results = [r for r in all_results if r["is_ood"]]

                    # If NO high-confidence results, return OOD message
                    if not high_confidence_results:
                        best_similarity = all_results[0]["similarity"] if all_results else 0
                        threshold_pct = int(embedding_service.SIMILARITY_THRESHOLD * 100)
                        logger.warning(
                            f"No relevant products found | query='{query}' | best_similarity={best_similarity*100:.1f}% | "
                            f"threshold={threshold_pct}%"
                        )
                        return (
                            f"⚠️ NO RELEVANT PRODUCTS FOUND\n\n"
                            f"Your query '{query}' did not match any products/services in our catalog.\n"
                            f"The search found {len(all_results)} result(s), but the best match had only "
                            f"{best_similarity*100:.1f}% similarity (threshold: {threshold_pct}%).\n\n"
                            f"This means we likely don't offer products/services related to '{query}'.\n"
                            f"Please inform the customer politely that this specific item/service is not available.\n\n"
                            f"💡 Suggestion: Ask the customer to clarify their request or check what we actually offer."
                        )

                    # Return only high-confidence results
                    results = high_confidence_results[:limit]

                    formatted_output = f"✅ Found {len(results)} relevant result(s) for query: '{query}'\n"

                    # Add info about filtered OOD results
                    if low_confidence_results:
                        formatted_output += f"(Filtered out {len(low_confidence_results)} low-confidence results)\n"

                    formatted_output += "\n"

                    for idx, result in enumerate(results, 1):
                        similarity = result["similarity"]
                        confidence_pct = int(similarity * 100)

                        formatted_output += f"[{idx}] {result['title']} (confidence: {confidence_pct}%)\n"
                        formatted_output += f"Description: {result['description']}\n"

                        if result["category"]:
                            formatted_output += f"Category: {result['category']}\n"

                        if result["price"]:
                            formatted_output += f"Price: {result['price']}\n"

                        if result["tags"]:
                            formatted_output += f"Tags: {result['tags']}\n"

                        if result["url"]:
                            formatted_output += f"URL: {result['url']}\n"

                        formatted_output += "\n"

                    # Add usage guidance
                    formatted_output += (
                        f"💡 Usage: These results are HIGH CONFIDENCE matches. "
                        f"You can safely use this information to answer the customer's question.\n"
                    )

                    avg_similarity = sum(r["similarity"] for r in results) / len(results) if results else 0
                    logger.info(
                        f"Embedding search completed | query='{query}' | results={len(results)} | "
                        f"avg_similarity={avg_similarity*100:.1f}% | ood_filtered={len(low_confidence_results)}"
                    )

                    return formatted_output

            except Exception as db_error:
                # Log the specific database error for debugging
                logger.error(f"Database error in embedding search | error={str(db_error)}", exc_info=True)
                # Return a user-friendly error message
                return (
                    f"⚠️ SEARCH TEMPORARILY UNAVAILABLE\n\n"
                    f"Sorry, the product search is temporarily unavailable due to high demand.\n"
                    f"Please try again in a moment or contact us directly for assistance.\n\n"
                    f"💡 Alternative: You can also browse our products on our website or send us a direct message."
                )

    except Exception as e:
        error_msg = f"❌ Error performing embedding search: {str(e)}"
        logger.error(f"Embedding search failed | error={str(e)}", exc_info=True)
        return error_msg


# Create the tool using @function_tool decorator
# This makes it available to OpenAI Agents SDK
embedding_search = function_tool(_embedding_search_implementation)
