"""Test script to verify carousel support works correctly."""

import asyncio
import sys
from sqlalchemy import select
from src.core.database import get_async_session
from src.core.models import Media
from src.core.services.media_service import MediaService
from src.core.services.instagram_service import InstagramGraphAPIService


async def test_image_post():
    """Test regular IMAGE post creation."""
    print("\n🧪 TEST 1: Regular IMAGE post")
    print("=" * 60)

    async for session in get_async_session():
        try:
            media_service = MediaService()

            # Check existing IMAGE post
            result = await session.execute(
                select(Media).where(Media.media_type == "IMAGE").limit(1)
            )
            media = result.scalar_one_or_none()

            if media:
                print(f"✅ Found IMAGE post: {media.id}")
                print(f"   Media type: {media.media_type}")
                print(f"   Media URL length: {len(media.media_url) if media.media_url else 0}")
                print(f"   Children URLs: {media.children_media_urls}")
                print(f"   Permalink length: {len(media.permalink)}")
                return True
            else:
                print("⚠️  No IMAGE posts found in database")
                return False

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False


async def test_carousel_structure():
    """Test that carousel structure supports long URLs."""
    print("\n🧪 TEST 2: Carousel structure validation")
    print("=" * 60)

    async for session in get_async_session():
        try:
            # Create a test carousel with very long URLs
            long_url = "https://scontent-fra5-1.cdninstagram.com/v/t51.82787-15/558731124_17849614362566616_6648017038430387400_n.jpg?stp=dst-jpg_e35_tt6&_nc_cat=100&ccb=1-7&_nc_sid=18de74&_nc_ohc=xyz123456789&_nc_ht=scontent-fra5-1.cdninstagram.com&edm=ANQ71j8EAAAA&_nc_gid=t8ILbfqn2OBqU7dkUGcsVw&oh=00_AfdKIlcNQCkrGkfnxk1sl2pScvoqwiYwGBcmc64C_TH3Bw&oe=68E9CF6F&extra_param_1=test&extra_param_2=test&extra_param_3=test"

            print(f"Testing with URL length: {len(long_url)} characters")

            test_media = Media(
                id="test_carousel_12345",
                permalink="https://www.instagram.com/p/TEST123/",
                media_type="CAROUSEL_ALBUM",
                media_url=long_url,
                children_media_urls=[long_url, long_url + "_2", long_url + "_3"],
                caption="Test carousel",
                username="test_user",
            )

            session.add(test_media)
            await session.commit()

            # Verify it was saved
            result = await session.execute(
                select(Media).where(Media.id == "test_carousel_12345")
            )
            saved_media = result.scalar_one_or_none()

            if saved_media:
                print(f"✅ Successfully saved carousel with long URLs")
                print(f"   Media URL: {saved_media.media_url[:80]}...")
                print(f"   Children count: {len(saved_media.children_media_urls)}")
                print(f"   First child URL length: {len(saved_media.children_media_urls[0])}")

                # Cleanup
                await session.delete(saved_media)
                await session.commit()
                print("✅ Test record cleaned up")
                return True
            else:
                print("❌ Failed to retrieve saved carousel")
                return False

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            await session.rollback()
            return False


async def test_extract_carousel_children():
    """Test _extract_carousel_children_urls method."""
    print("\n🧪 TEST 3: Extract carousel children URLs")
    print("=" * 60)

    try:
        media_service = MediaService()

        # Mock Instagram API response for carousel
        mock_response = {
            "media_type": "CAROUSEL_ALBUM",
            "children": {
                "data": [
                    {"id": "1", "media_url": "https://example.com/img1.jpg", "media_type": "IMAGE"},
                    {"id": "2", "media_url": "https://example.com/img2.jpg", "media_type": "IMAGE"},
                    {"id": "3", "media_url": "https://example.com/img3.jpg", "media_type": "IMAGE"},
                ]
            }
        }

        children_urls = media_service._extract_carousel_children_urls(mock_response)

        if children_urls and len(children_urls) == 3:
            print(f"✅ Successfully extracted {len(children_urls)} children URLs")
            for i, url in enumerate(children_urls, 1):
                print(f"   [{i}] {url}")
            return True
        else:
            print(f"❌ Expected 3 URLs, got {len(children_urls) if children_urls else 0}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_non_carousel():
    """Test that non-carousel posts return None for children extraction."""
    print("\n🧪 TEST 4: Non-carousel handling")
    print("=" * 60)

    try:
        media_service = MediaService()

        # Mock Instagram API response for IMAGE
        mock_response = {
            "media_type": "IMAGE",
            "media_url": "https://example.com/img.jpg"
        }

        children_urls = media_service._extract_carousel_children_urls(mock_response)

        if children_urls is None:
            print(f"✅ Correctly returned None for non-carousel")
            return True
        else:
            print(f"❌ Expected None, got {children_urls}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🚀 CAROUSEL SUPPORT TESTS")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Regular IMAGE post", await test_image_post()))
    results.append(("Carousel structure", await test_carousel_structure()))
    results.append(("Extract children URLs", await test_extract_carousel_children()))
    results.append(("Non-carousel handling", await test_non_carousel()))

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
