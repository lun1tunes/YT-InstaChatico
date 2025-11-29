#!/usr/bin/env python3
"""Populate database with sample products and embeddings for testing"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from core.config import settings
from core.services.embedding_service import EmbeddingService


# Sample products/services (customize these for your business)
SAMPLE_PRODUCTS = [
    {
        "title": "Квартира в центре города",
        "description": "Просторная двухкомнатная квартира в центре города, 65 кв.м., с ремонтом и мебелью. Рядом метро, парковка, развитая инфраструктура.",
        "category": "Недвижимость",
        "price": "5 000 000 руб.",
        "tags": "квартира, недвижимость, центр, двухкомнатная",
        "url": "https://example.com/apartments/center-1",
        "image_url": "https://example.com/images/apt1.jpg"
    },
    {
        "title": "Апартаменты у моря",
        "description": "Новые апартаменты на берегу моря, 50 кв.м., панорамные окна с видом на море. Идеально для отдыха и инвестиций.",
        "category": "Недвижимость",
        "price": "8 000 000 руб.",
        "tags": "апартаменты, море, панорамные окна, инвестиции",
        "url": "https://example.com/apartments/seaside-1",
        "image_url": "https://example.com/images/apt2.jpg"
    },
    {
        "title": "Коттедж в пригороде",
        "description": "Уютный коттедж на участке 10 соток, 120 кв.м., 3 спальни, баня, гараж. Тихое место для семейного отдыха.",
        "category": "Недвижимость",
        "price": "12 000 000 руб.",
        "tags": "коттедж, дом, пригород, участок, баня",
        "url": "https://example.com/houses/cottage-1",
        "image_url": "https://example.com/images/cottage1.jpg"
    },
    {
        "title": "Консультация по недвижимости",
        "description": "Профессиональная консультация по подбору недвижимости. Поможем выбрать квартиру, дом или коммерческую недвижимость под ваши требования.",
        "category": "Услуги",
        "price": "Бесплатно",
        "tags": "консультация, услуги, помощь, подбор",
        "url": "https://example.com/services/consultation",
        "image_url": "https://example.com/images/consultation.jpg"
    },
    {
        "title": "Юридическое сопровождение сделки",
        "description": "Полное юридическое сопровождение сделок с недвижимостью. Проверка документов, регистрация, безопасность сделки.",
        "category": "Услуги",
        "price": "50 000 руб.",
        "tags": "юридические услуги, сделка, документы, безопасность",
        "url": "https://example.com/services/legal",
        "image_url": "https://example.com/images/legal.jpg"
    },
    {
        "title": "Студия в новостройке",
        "description": "Студия 28 кв.м. в новом жилом комплексе. Современная планировка, высокие потолки, сдача дома в 2025 году.",
        "category": "Недвижимость",
        "price": "3 500 000 руб.",
        "tags": "студия, новостройка, современная, инвестиции",
        "url": "https://example.com/apartments/studio-1",
        "image_url": "https://example.com/images/studio1.jpg"
    },
    {
        "title": "Пентхаус с террасой",
        "description": "Эксклюзивный пентхаус 200 кв.м. с террасой 80 кв.м. Премиум-класс, панорамный вид на город, дизайнерский ремонт.",
        "category": "Недвижимость",
        "price": "35 000 000 руб.",
        "tags": "пентхаус, терраса, премиум, эксклюзив, панорама",
        "url": "https://example.com/apartments/penthouse-1",
        "image_url": "https://example.com/images/penthouse1.jpg"
    },
    {
        "title": "Ипотечное консультирование",
        "description": "Помощь в оформлении ипотеки. Подбор лучших условий, работа с банками, одобрение за 1 день. Более 20 банков-партнеров.",
        "category": "Услуги",
        "price": "От 10 000 руб.",
        "tags": "ипотека, кредит, банки, финансы",
        "url": "https://example.com/services/mortgage",
        "image_url": "https://example.com/images/mortgage.jpg"
    },
]


async def populate_embeddings():
    """Add sample products with auto-generated embeddings to database"""
    print("🚀 Starting database population...")

    # Create database connection
    engine = create_async_engine(settings.db.url, echo=False)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False)

    async with session_factory() as session:
        try:
            # Initialize embedding service
            embedding_service = EmbeddingService()

            print(f"\n📦 Adding {len(SAMPLE_PRODUCTS)} products...\n")

            for idx, product_data in enumerate(SAMPLE_PRODUCTS, 1):
                try:
                    print(f"[{idx}/{len(SAMPLE_PRODUCTS)}] Adding: {product_data['title']}")

                    # Add product to database (will automatically generate embedding)
                    product = await embedding_service.add_product(
                        title=product_data["title"],
                        description=product_data["description"],
                        session=session,
                        category=product_data.get("category"),
                        price=product_data.get("price"),
                        tags=product_data.get("tags"),
                        url=product_data.get("url"),
                        image_url=product_data.get("image_url"),
                        is_active=True
                    )

                    print(f"    ✅ Added successfully (ID: {product.id})")

                except Exception as e:
                    print(f"    ❌ Failed to add: {e}")

            print("\n✨ Database population completed!")
            print("\n📊 Testing search functionality...\n")

            # Test search
            test_queries = [
                "квартиры в центре",
                "консультация",
                "премиум недвижимость"
            ]

            for query in test_queries:
                print(f"🔍 Searching for: '{query}'")
                results = await embedding_service.search_similar_products(
                    query=query,
                    session=session,
                    limit=3
                )

                if results:
                    for result in results:
                        print(f"    - {result['title']} (similarity: {result['similarity']:.4f})")
                else:
                    print("    No results found")
                print()

        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise
        finally:
            await engine.dispose()

    print("✅ All done!")


if __name__ == "__main__":
    asyncio.run(populate_embeddings())
