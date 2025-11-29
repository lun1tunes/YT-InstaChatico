"""Service for analyzing media images using AI."""

import logging
import asyncio
from typing import Optional, List

from .base_service import BaseService
from ..agents.tools.web_image_analyzer_tool import _analyze_image_implementation

logger = logging.getLogger(__name__)


class MediaAnalysisService(BaseService):
    """Analyze media images using OpenAI Vision API."""

    async def analyze_carousel_images(
        self, media_urls: List[str], caption: Optional[str] = None
    ) -> Optional[str]:
        """
        Analyze multiple images from a carousel post and combine their descriptions.

        Args:
            media_urls: List of media image URLs to analyze
            caption: Optional caption text to provide additional context

        Returns:
            Combined detailed context description or None if analysis fails
        """
        try:
            logger.info(f"Starting carousel analysis for {len(media_urls)} images")

            if not media_urls:
                logger.warning("Empty media_urls list provided")
                return None

            # Prepare context for carousel analysis
            additional_context = f"""Это изображение из карусели Instagram (пост с несколькими изображениями). Это изображение {{image_index}} из {len(media_urls)}.
Проанализируй его детально для использования в ответах на комментарии клиентов.

ВАЖНО: При описании продуктов используй РУССКИЕ ТЕРМИНЫ и КАТЕГОРИИ, а не английские названия брендов.

Примеры:
- ❌ НЕПРАВИЛЬНО: "Lumiere Coffee Scrub"
- ✅ ПРАВИЛЬНО: "кофейный скраб для тела антицеллюлитный"

Описывай продукты через их НАЗНАЧЕНИЕ и ХАРАКТЕРИСТИКИ на русском языке."""

            if caption:
                additional_context += f"\n\nПодпись к карусели: {caption}"

            # Analyze all images in parallel
            tasks = []
            for idx, url in enumerate(media_urls, 1):
                context_with_index = additional_context.replace("{image_index}", str(idx))
                tasks.append(self._analyze_single_image(url, context_with_index))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out errors and combine results
            valid_results = []
            for idx, result in enumerate(results, 1):
                if isinstance(result, Exception):
                    logger.error(f"Error analyzing image {idx}/{len(media_urls)}: {result}")
                    continue
                if result and not result.startswith("Ошибка"):
                    valid_results.append(f"[Изображение {idx}]: {result}")
                else:
                    logger.warning(f"Image {idx}/{len(media_urls)} analysis failed or returned error")

            if not valid_results:
                logger.error("All carousel images failed to analyze")
                return None

            # Combine all descriptions
            combined_context = f"Пост-карусель из {len(media_urls)} изображений.\n\n" + "\n\n".join(valid_results)

            logger.info(
                f"Carousel analysis completed. Analyzed {len(valid_results)}/{len(media_urls)} images successfully. "
                f"Context length: {len(combined_context)} characters"
            )

            return combined_context

        except Exception as e:
            logger.error(f"Error analyzing carousel images: {e}")
            logger.exception("Full traceback:")
            return None

    async def _analyze_single_image(self, media_url: str, additional_context: str) -> Optional[str]:
        """Helper method to analyze a single image."""
        try:
            result = await _analyze_image_implementation(
                image_url=media_url,
                additional_context=additional_context
            )
            return result
        except Exception as e:
            logger.error(f"Error in _analyze_single_image for {media_url}: {e}")
            raise

    async def analyze_media_image(self, media_url: str, caption: Optional[str] = None) -> Optional[str]:
        """
        Analyze media image and generate detailed context description.

        Args:
            media_url: URL of the media image to analyze
            caption: Optional caption text to provide additional context

        Returns:
            Detailed context description or None if analysis fails
        """
        try:
            logger.info(f"Starting media analysis for URL: {media_url[:100]}...")

            # Prepare context for the image analysis
            additional_context = """Это изображение из поста Instagram. Проанализируй его детально для использования в ответах на комментарии клиентов.

ВАЖНО: При описании продуктов используй РУССКИЕ ТЕРМИНЫ и КАТЕГОРИИ, а не английские названия брендов.

Примеры:
- ❌ НЕПРАВИЛЬНО: "Lumiere Coffee Scrub"
- ✅ ПРАВИЛЬНО: "кофейный скраб для тела антицеллюлитный"

- ❌ НЕПРАВИЛЬНО: "Keratin Shampoo"
- ✅ ПРАВИЛЬНО: "кератиновый шампунь для восстановления волос"

- ❌ НЕПРАВИЛЬНО: "Vitamin C Serum"
- ✅ ПРАВИЛЬНО: "сыворотка с витамином С для лица"

Описывай продукты через их НАЗНАЧЕНИЕ и ХАРАКТЕРИСТИКИ на русском языке, чтобы клиенты могли легко их найти."""

            if caption:
                additional_context += f"\n\nПодпись к посту: {caption}"
                additional_context += "\n\nИзвлеки всю информацию, которая может быть полезна для ответов на вопросы клиентов о продуктах, услугах, ценах. Используй русские термины для описания продуктов."

            # Call the image analyzer tool directly (no agent wrapper needed)
            analysis_result = await _analyze_image_implementation(
                image_url=media_url,
                additional_context=additional_context
            )

            if not analysis_result:
                logger.warning(f"Image analysis returned empty result for {media_url}")
                return None

            # Check if it's an error message
            if analysis_result.startswith("Ошибка"):
                logger.error(f"Image analysis failed: {analysis_result}")
                return None

            logger.info(f"Media analysis completed. Context length: {len(analysis_result)} characters")

            return analysis_result

        except Exception as e:
            logger.error(f"Error analyzing media image {media_url}: {e}")
            logger.exception("Full traceback:")
            return None
