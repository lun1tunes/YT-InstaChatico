#!/usr/bin/env python3
"""
Load test data for development and testing.
Populates product_embeddings and media tables with realistic personal care products.

Usage:
    python scripts/load_test_data.py [--clean] [--products-only] [--media-only]

Options:
    --clean         Remove all test data before loading
    --products-only Load only products (skip media)
    --media-only    Load only media (skip products)
"""

import asyncio
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import select, delete

from core.models.product_embedding import ProductEmbedding
from core.models.media import Media
from core.services.embedding_service import EmbeddingService
from core.container import get_container

# Import test data
from test_data.personal_care_products import PERSONAL_CARE_PRODUCTS, MEDIA_TEST_DATA

# Color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")


def print_error(text):
    print(f"{RED}❌ {text}{RESET}")


def print_info(text):
    print(f"{YELLOW}ℹ️  {text}{RESET}")


def print_header(text):
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{text.center(80)}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")


async def clean_test_data(session):
    """Remove all test data from database"""
    print_header("Cleaning Test Data")

    try:
        # Clean products (all products are considered test data)
        result = await session.execute(delete(ProductEmbedding))
        products_deleted = result.rowcount

        # Clean test media (only media with test_ prefix)
        result = await session.execute(delete(Media).where(Media.id.like("test_%")))
        media_deleted = result.rowcount

        await session.commit()

        print_success(f"Deleted {products_deleted} products")
        print_success(f"Deleted {media_deleted} test media records")

        return products_deleted, media_deleted

    except Exception as e:
        await session.rollback()
        print_error(f"Error cleaning data: {e}")
        raise


async def load_products(session):
    """Load product embeddings"""
    print_header("Loading Product Embeddings")

    embedding_service = EmbeddingService()
    success_count = 0
    error_count = 0

    print_info(f"Loading {len(PERSONAL_CARE_PRODUCTS)} products...")

    for idx, product in enumerate(PERSONAL_CARE_PRODUCTS, 1):
        try:
            # Check if product already exists (by title)
            existing = await session.execute(select(ProductEmbedding).where(ProductEmbedding.title == product["title"]))
            if existing.scalar_one_or_none():
                print_info(f"[{idx}/{len(PERSONAL_CARE_PRODUCTS)}] Skipped (exists): {product['title'][:50]}...")
                continue

            # Add product with embedding
            await embedding_service.add_product(
                title=product["title"],
                description=product["description"],
                session=session,
                category=product.get("category"),
                price=product.get("price"),
                tags=product.get("tags"),
                url=product.get("url"),
                image_url=product.get("image_url"),
            )

            success_count += 1
            print_success(f"[{idx}/{len(PERSONAL_CARE_PRODUCTS)}] Added: {product['title'][:50]}...")

        except Exception as e:
            error_count += 1
            print_error(f"[{idx}/{len(PERSONAL_CARE_PRODUCTS)}] Failed: {product['title'][:50]}")
            print_error(f"  Error: {str(e)[:100]}")

    await session.commit()

    print(f"\n{GREEN}Products loaded: {success_count}{RESET}")
    if error_count > 0:
        print(f"{RED}Errors: {error_count}{RESET}")

    return success_count, error_count


async def load_media(session):
    """Load test media records"""
    print_header("Loading Test Media")

    success_count = 0
    error_count = 0

    print_info(f"Loading {len(MEDIA_TEST_DATA)} media records...")

    for idx, media_data in enumerate(MEDIA_TEST_DATA, 1):
        try:
            # Check if media already exists
            existing = await session.execute(select(Media).where(Media.id == media_data["id"]))
            if existing.scalar_one_or_none():
                print_info(f"[{idx}/{len(MEDIA_TEST_DATA)}] Skipped (exists): {media_data['id']}")
                continue

            # Create media record
            media = Media(
                id=media_data["id"],
                permalink=media_data["permalink"],
                caption=media_data.get("caption"),
                media_url=media_data.get("media_url"),
                media_type=media_data.get("media_type", "IMAGE"),
                username=media_data.get("username", "test_user"),
                owner=media_data.get("owner"),
                comments_count=media_data.get("comments_count", 0),
                like_count=media_data.get("like_count", 0),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                raw_data={"test": True},
            )

            session.add(media)
            success_count += 1
            print_success(f"[{idx}/{len(MEDIA_TEST_DATA)}] Added: {media_data['id']}")

        except Exception as e:
            error_count += 1
            print_error(f"[{idx}/{len(MEDIA_TEST_DATA)}] Failed: {media_data['id']}")
            print_error(f"  Error: {str(e)[:100]}")

    await session.commit()

    print(f"\n{GREEN}Media records loaded: {success_count}{RESET}")
    if error_count > 0:
        print(f"{RED}Errors: {error_count}{RESET}")

    return success_count, error_count


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="Load test data for development")
    parser.add_argument("--clean", action="store_true", help="Clean existing test data first")
    parser.add_argument("--products-only", action="store_true", help="Load only products")
    parser.add_argument("--media-only", action="store_true", help="Load only media")
    args = parser.parse_args()

    print_header("Test Data Loader - Personal Care Products")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    container = get_container()
    session_factory = container.db_session_factory()

    async with session_factory() as session:
        try:
            # Clean if requested
            if args.clean:
                await clean_test_data(session)

            # Load data
            if not args.media_only:
                products_success, products_errors = await load_products(session)
            else:
                products_success, products_errors = 0, 0

            if not args.products_only:
                media_success, media_errors = await load_media(session)
            else:
                media_success, media_errors = 0, 0

            # Summary
            print_header("Summary")
            print(f"Products loaded: {GREEN}{products_success}{RESET}")
            print(f"Media loaded: {GREEN}{media_success}{RESET}")

            total_errors = products_errors + media_errors
            if total_errors > 0:
                print(f"Total errors: {RED}{total_errors}{RESET}")
            else:
                print_success("All data loaded successfully! 🎉")

            print("\n")
            print_info("Test your products with:")
            print("  python scripts/test_ood_detection.py")
            print("\n")
            print_info("Or use the test endpoint:")
            print("  curl -X POST http://localhost:4291/api/v1/webhook/test \\")
            print('    -H "Content-Type: application/json" \\')
            print("    -d '{")
            print('      "comment_id": "test_001",')
            print('      "media_id": "test_media_skincare_001",')
            print('      "user_id": "user_001",')
            print('      "username": "customer",')
            print('      "text": "Какие у вас есть сыворотки для лица?"')
            print("    }'")

        except Exception as e:
            print_error(f"Fatal error: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
