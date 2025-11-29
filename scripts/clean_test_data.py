#!/usr/bin/env python3
"""
Clean test data from database.
Removes all product embeddings and test media records.

Usage:
    python scripts/clean_test_data.py [--confirm] [--products-only] [--media-only] [--comments-only]

Options:
    --confirm        Skip confirmation prompt
    --products-only  Clean only products
    --media-only     Clean only media
    --comments-only  Clean only test comments (keeps products and media)
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, delete, func

from core.config import settings
from core.models.product_embedding import ProductEmbedding
from core.models.media import Media
from core.models.instagram_comment import InstagramComment

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


def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{RESET}")


def print_info(text):
    print(f"{YELLOW}ℹ️  {text}{RESET}")


def print_header(text):
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{text.center(80)}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")


async def count_records(session):
    """Count records that will be deleted"""
    # Count products
    products_result = await session.execute(select(func.count(ProductEmbedding.id)))
    products_count = products_result.scalar()

    # Count test media
    media_result = await session.execute(select(func.count(Media.id)).where(Media.id.like("test_%")))
    media_count = media_result.scalar()

    # Count test comments
    comments_result = await session.execute(
        select(func.count(InstagramComment.id)).where(InstagramComment.id.like("test_%"))
    )
    comments_count = comments_result.scalar()

    return products_count, media_count, comments_count


async def clean_products(session):
    """Remove all product embeddings"""
    result = await session.execute(delete(ProductEmbedding))
    count = result.rowcount
    await session.commit()
    return count


async def clean_media(session):
    """Remove test media records"""
    result = await session.execute(delete(Media).where(Media.id.like("test_%")))
    count = result.rowcount
    await session.commit()
    return count


async def clean_comments(session):
    """Remove test comments and related records"""
    # Delete comments (cascade will handle classifications and answers)
    result = await session.execute(delete(InstagramComment).where(InstagramComment.id.like("test_%")))
    count = result.rowcount
    await session.commit()
    return count


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="Clean test data from database")
    parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--products-only", action="store_true", help="Clean only products")
    parser.add_argument("--media-only", action="store_true", help="Clean only media")
    parser.add_argument("--comments-only", action="store_true", help="Clean only test comments")
    args = parser.parse_args()

    print_header("Test Data Cleaner")

    # Create database connection
    engine = create_async_engine(settings.db.url, echo=False)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False)

    async with session_factory() as session:
        try:
            # Count records
            print_info("Counting records to delete...")
            products_count, media_count, comments_count = await count_records(session)

            print(f"\nRecords to delete:")
            if not args.media_only and not args.comments_only:
                print(f"  Products: {YELLOW}{products_count}{RESET}")
            if not args.products_only and not args.comments_only:
                print(f"  Test media: {YELLOW}{media_count}{RESET}")
            if not args.products_only and not args.media_only:
                print(f"  Test comments: {YELLOW}{comments_count}{RESET}")

            total = 0
            if not args.media_only and not args.comments_only:
                total += products_count
            if not args.products_only and not args.comments_only:
                total += media_count
            if not args.products_only and not args.media_only:
                total += comments_count

            if total == 0:
                print_success("\nNo test data found. Database is clean! ✨")
                return

            # Confirmation
            if not args.confirm:
                print_warning(f"\nThis will delete {total} record(s)!")
                response = input(f"{YELLOW}Are you sure? (yes/no): {RESET}").strip().lower()
                if response not in ["yes", "y"]:
                    print_info("Operation cancelled.")
                    return

            # Clean data
            print_header("Cleaning Data")

            deleted_products = 0
            deleted_media = 0
            deleted_comments = 0

            if not args.media_only and not args.comments_only:
                print_info("Deleting products...")
                deleted_products = await clean_products(session)
                print_success(f"Deleted {deleted_products} products")

            if not args.products_only and not args.comments_only:
                print_info("Deleting test media...")
                deleted_media = await clean_media(session)
                print_success(f"Deleted {deleted_media} media records")

            if not args.products_only and not args.media_only:
                print_info("Deleting test comments...")
                deleted_comments = await clean_comments(session)
                print_success(f"Deleted {deleted_comments} comments")

            # Summary
            print_header("Summary")
            total_deleted = deleted_products + deleted_media + deleted_comments
            print_success(f"Total records deleted: {total_deleted}")
            print_success("Database cleaned successfully! ✨")

            print("\n")
            print_info("To reload test data, run:")
            print("  python scripts/load_test_data.py")

        except Exception as e:
            print_error(f"Error: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
