"""
Image analysis tool using OpenAI Vision API for Instagram media.
Extracts text, prices, financial data, and visual descriptions from images.
"""

import logging
import base64
from typing import Optional
import aiohttp
from openai import AsyncOpenAI
from ...config import settings
from ...utils.comment_context import get_comment_context
from agents import function_tool

logger = logging.getLogger(__name__)

# Suppress verbose HTTP client logs that include large base64 image data
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# Configuration constants (DRY principle - single source of truth)
IMAGE_DOWNLOAD_TIMEOUT = 30  # seconds
IMAGE_ANALYSIS_MODEL = "gpt-4o"  # GPT-4o for image analysis
IMAGE_ANALYSIS_MAX_TOKENS = 2000
IMAGE_ANALYSIS_TEMPERATURE = 0.1  # Low temperature for precise analysis
IMAGE_DETAIL_LEVEL = "high"  # High quality for detailed analysis


async def _analyze_image_implementation(image_url: str, additional_context: Optional[str] = None) -> str:
    """
    Анализ изображений по URL с помощью OpenAI Vision API для извлечения детальной визуальной информации.

    Этот инструмент специализируется на анализе изображений, прикрепленных к постам или комментариям Instagram.
    Он может извлекать текст, финансовые данные, цены, расписания, детали продуктов и описывать
    визуальный контент. Используй его, когда клиент ссылается на изображение или когда пост содержит медиа.

    ИСПОЛЬЗУЙ ЭТОТ ИНСТРУМЕНТ КОГДА:
    - Пост/комментарий Instagram содержит изображение, требующее анализа
    - Клиент спрашивает о том, что видно на изображении ("Что показано на картинке?")
    - Нужно извлечь текст из изображений (цены, расписания, контактная информация)
    - Финансовые графики или диаграммы требуют интерпретации
    - Изображения продуктов требуют детального описания

    НЕ ИСПОЛЬЗУЙ когда:
    - URL изображения недоступен
    - На вопрос можно ответить без просмотра изображения

    ВОЗМОЖНОСТИ:
    - Извлечение всего видимого текста на изображении (OCR)
    - Анализ финансовых графиков: цены, тренды, проценты, даты
    - Описание продуктов, услуг и рекламных предложений
    - Чтение расписаний, календарей и информации о мероприятиях
    - Определение ключевых визуальных элементов, композиции и стиля

    Args:
        image_url: Полный URL изображения для анализа. Должен быть валидным HTTP/HTTPS URL,
                  указывающим на доступное изображение (JPG, PNG и т.д.). Изображение будет
                  загружено и проанализировано OpenAI Vision API в режиме высокой детализации.
        additional_context: Необязательная контекстная информация об изображении для улучшения
                          точности анализа (например, "Это из поста о квартирах",
                          "Клиент спрашивает о ценах на этом изображении"). Предоставление
                          контекста помогает сфокусировать анализ на релевантных деталях.

    Returns:
        Детальный анализ содержимого изображения в виде строки, включающий:
        - Весь видимый текст и числа, извлеченные из изображения
        - Описания ключевых визуальных элементов
        - Интерпретацию финансовых данных, если присутствуют (цены, тренды, проценты)
        - Структурированную информацию (даты, время, местоположения), если присутствует
        - Общее описание композиции и стиля
        Анализ оптимизирован для ответов на вопросы клиентов на основе содержимого изображения.

    Examples:
        Базовое использование:
        - image_url: "https://example.com/apartment.jpg"
          Вернет: Детальное описание характеристик квартиры, видимых на фото

        С контекстом:
        - image_url: "https://example.com/price_chart.jpg"
          additional_context: "Клиент спрашивает об исторических ценах"
          Вернет: Анализ, сфокусированный на ценовых трендах и конкретных значениях на графике

        Обработка ошибок:
        - Если URL недействителен или изображение недоступно, вернет сообщение об ошибке
        - Если анализ не удался, вернет описательную ошибку для устранения неполадок
    """
    try:
        logger.info(f"Image analysis started | url_length={len(image_url)} | has_context={bool(additional_context)}")

        # Download the image first (Instagram URLs require this)
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=IMAGE_DOWNLOAD_TIMEOUT)) as response:
                if response.status != 200:
                    error_msg = f"Image download failed | status={response.status}"
                    logger.error(error_msg)
                    raise Exception(f"Failed to download image: HTTP {response.status}")

                # Determine image format from content-type or default to jpeg
                content_type = response.headers.get("content-type", "image/jpeg")
                image_data = await response.read()

        # Encode image to base64
        base64_image = base64.b64encode(image_data).decode("utf-8")
        if "png" in content_type:
            image_format = "png"
        elif "webp" in content_type:
            image_format = "webp"
        elif "gif" in content_type:
            image_format = "gif"
        else:
            image_format = "jpeg"

        logger.debug(f"Image downloaded | size_bytes={len(image_data)} | format={image_format}")

        # Базовый промт с подробными инструкциями
        base_prompt = """
        Ты - эксперт по анализу изображений с особым фокусом на извлечение максимально полной информации.
        
        Твоя задача - детально анализировать изображение и извлекать всю доступную информацию.
        
        Для финансовых графиков и диаграмм ОБЯЗАТЕЛЬНО:
        - Внимательно анализируй ВСЕ цифры, цены, даты на графике
        - Определяй тренды: рост, падение, стабильность
        - Извлекай конкретные значения: цены, проценты, временные периоды
        - Анализируй масштаб и единицы измерения
        - Определяй тип графика: линейный, свечной, гистограмма, круговая диаграмма
        - Выделяй ключевые точки: максимумы, минимумы, развороты
        - Обращай внимание на подписи осей, легенды, заголовки
        - Если видишь конкретные числа - обязательно их указывай точно
        
        Для изображений с описанием акций или услуг:
        - Извлекай всю текстовую информацию
        - Выделяй названия компаний, продуктов, услуг
        - Указывай цены, скидки, акции
        - Определяй контактную информацию
        - Выделяй ключевые преимущества и особенности
        
        Для расписаний и календарей:
        - Извлекай все даты и время
        - Определяй события, встречи, мероприятия
        - Указывай места проведения
        - Выделяй участников и организаторов
        
        Для обычных изображений:
        - Описывай что изображено
        - Указывай стиль, композицию, цвета
        - Выделяй ключевые элементы
        - Определяй эмоциональную окраску
        
        Всегда будь точным и объективным в описаниях. Извлекай максимум информации из визуального контента.
        """

        # Добавляем дополнительный контекст если предоставлен
        if additional_context:
            prompt = f"{base_prompt}\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ: {additional_context}"
        else:
            prompt = base_prompt

        # Инициализируем OpenAI клиент с автоматическим закрытием (async context manager)
        async with AsyncOpenAI(api_key=settings.openai.api_key) as client:
            # Вызываем OpenAI Vision API with base64 encoded image
            api_response = await client.chat.completions.create(
                model=IMAGE_ANALYSIS_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image_format};base64,{base64_image}",
                                    "detail": IMAGE_DETAIL_LEVEL,
                                },
                            },
                        ],
                    }
                ],
                max_tokens=IMAGE_ANALYSIS_MAX_TOKENS,
                temperature=IMAGE_ANALYSIS_TEMPERATURE,
            )

            # Извлекаем результат
            analysis_result = api_response.choices[0].message.content

            # Get token usage from response
            input_tokens = getattr(api_response.usage, "prompt_tokens", 0) if api_response.usage else 0
            output_tokens = getattr(api_response.usage, "completion_tokens", 0) if api_response.usage else 0

            logger.info(
                f"Image analysis completed | result_length={len(analysis_result)} | "
                f"input_tokens={input_tokens} | output_tokens={output_tokens}"
            )

            from ...container import get_container  # local import to avoid circular dependency

            try:
                inspector = get_container().tools_token_usage_inspector(session=None)
                ctx = get_comment_context()
                comment_ref = ctx.get("comment_id")
                await inspector.record(
                    tool="web_image_analyzer_tool",
                    task="media_image_analysis",
                    model=IMAGE_ANALYSIS_MODEL,
                    tokens_in=input_tokens,
                    tokens_out=output_tokens,
                    comment_id=comment_ref,
                    metadata={
                        "image_url": image_url,
                        "additional_context": additional_context[:200] if additional_context else None,
                    },
                )
            except Exception:
                logger.debug("Skipping token usage logging for vision tool", exc_info=True)

            return analysis_result

    except Exception as e:
        logger.error(f"Image analysis failed | error={str(e)}", exc_info=True)
        return f"Ошибка при анализе изображения: {str(e)}"


# Создаем инструмент с декоратором @function_tool
analyze_image_async = function_tool(_analyze_image_implementation)
