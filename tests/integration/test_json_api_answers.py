"""Answer management and deletion tests for JSON API endpoints."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

from core.models import CommentClassification, InstagramComment, Media, QuestionAnswer
from core.models.comment_classification import ProcessingStatus
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers
from sqlalchemy import select


# ===== Answer Listing Tests =====


@pytest.mark.asyncio
async def test_list_answers_for_comment(integration_environment):
    """Test listing answers for a comment."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_answer_list",
            permalink="https://instagram.com/p/media_answer_list",
            media_type="IMAGE",
            media_url="https://cdn.test/answer_list.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_with_answer",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Question?",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Here is the answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            reply_sent=False,
            processing_status="COMPLETED",
        )
        session.add(answer)
        await session.commit()

    response = await client.get(
        "/api/v1/comments/comment_with_answer/answers",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 1
    assert payload[0]["answer"] == "Here is the answer"
    assert payload[0]["is_deleted"] is False


@pytest.mark.asyncio
async def test_list_answers_empty(integration_environment):
    """Test listing answers for comment without answers."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_no_answer",
            permalink="https://instagram.com/p/media_no_answer",
            media_type="IMAGE",
            media_url="https://cdn.test/no_answer.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_no_answer",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="No answer yet",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.get(
        "/api/v1/comments/comment_no_answer/answers",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 0


# ============================================================================
# Answer Deletion with Instagram Reply Flow Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_answer_with_instagram_reply_success(integration_environment):
    """Test successful deletion of answer with Instagram reply."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    # Setup: Create comment with answer that has been sent as reply
    async with session_factory() as session:
        media = Media(
            id="media_del_answer",
            permalink="https://instagram.com/p/media_del_answer",
            media_type="IMAGE",
            media_url="https://cdn.test/media_del_answer.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.flush()

        comment = InstagramComment(
            id="comment_del_answer",
            media_id=media.id,
            user_id="user_del",
            username="user_del",
            text="Test question",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.flush()

        classification = CommentClassification(
            comment_id=comment.id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        session.add(classification)
        await session.flush()

        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Test answer response",
            reply_sent=True,
            reply_status="sent",
            reply_id="reply_del_test_123",
            reply_sent_at=now_db_utc(),
        )
        session.add(answer)
        await session.commit()
        answer_id = answer.id

    # Simulate reply in Instagram stub
    instagram_service.replies.append({
        "comment_id": "comment_del_answer",
        "reply_id": "reply_del_test_123",
        "message": "Test answer response",
    })

    # Action: DELETE the answer
    response = await client.delete(
        f"/api/v1/answers/{answer_id}",
        headers=auth_headers(integration_environment),
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["error"] is None

    # Verify Instagram reply was deleted
    assert len(instagram_service.replies) == 0

    # Verify answer still exists in DB but marked as deleted
    async with session_factory() as session:
        deleted_answer = await session.get(QuestionAnswer, answer_id)
        assert deleted_answer is not None  # Answer persists in DB
        assert deleted_answer.reply_sent is False
        assert deleted_answer.reply_status == "deleted"
        assert deleted_answer.reply_error is None
        assert deleted_answer.is_deleted is True
        # Original fields unchanged
        assert deleted_answer.answer == "Test answer response"
        assert deleted_answer.reply_id == "reply_del_test_123"


@pytest.mark.asyncio
async def test_delete_answer_without_reply_id_fails(integration_environment):
    """Test deletion fails with 400 when answer has no reply_id."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Setup: Create answer without reply_id
    async with session_factory() as session:
        media = Media(
            id="media_no_reply",
            permalink="https://instagram.com/p/media_no_reply",
            media_type="IMAGE",
            media_url="https://cdn.test/media_no_reply.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_no_reply",
            media_id=media.id,
            user_id="user_no_reply",
            username="user_no_reply",
            text="Question",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.flush()

        classification = CommentClassification(
            comment_id=comment.id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        session.add(classification)

        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Generated answer",
            reply_sent=False,
            reply_status=None,
            reply_id=None,  # No reply_id
        )
        session.add(answer)
        await session.commit()
        answer_id = answer.id

    # Action: Attempt to delete
    response = await client.delete(
        f"/api/v1/answers/{answer_id}",
        headers=auth_headers(integration_environment),
    )

    # Verify error response
    assert response.status_code == 400
    data = response.json()
    # Success is False when error is present
    assert data["meta"]["error"]["code"] == 4012
    assert "does not have an Instagram reply" in data["meta"]["error"]["message"]


@pytest.mark.asyncio
async def test_patch_answer_replaces_reply_success(integration_environment):
    """Manual patch replaces Instagram reply and persists new active answer."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_patch_answer",
            permalink="https://instagram.com/p/media_patch_answer",
            media_type="IMAGE",
            media_url="https://cdn.test/media_patch_answer.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.flush()

        comment = InstagramComment(
            id="comment_patch_answer",
            media_id=media.id,
            user_id="user_patch",
            username="user_patch",
            text="Need a better answer",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.flush()

        session.add(
            CommentClassification(
                comment_id=comment.id,
                processing_status=ProcessingStatus.COMPLETED,
            )
        )

        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Original bot reply",
            answer_confidence=0.65,
            answer_quality_score=60,
            reply_sent=True,
            reply_status="sent",
            reply_id="reply-original-999",
            reply_sent_at=now_db_utc(),
        )
        session.add(answer)
        await session.commit()
        old_answer_id = answer.id

    instagram_service.replies.append(
        {
            "comment_id": "comment_patch_answer",
            "reply_id": "reply-original-999",
            "message": "Original bot reply",
        }
    )

    response = await client.patch(
        f"/api/v1/answers/{old_answer_id}",
        json={"answer": "Updated manual reply", "quality_score": 95, "confidence": 10},
        headers=auth_headers(integration_environment),
    )

    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["answer"] == "Updated manual reply"
    assert payload["confidence"] == 100
    assert payload["quality_score"] == 100
    assert payload["is_deleted"] is False
    assert payload["id"] != old_answer_id

    assert all(reply["reply_id"] != "reply-original-999" for reply in instagram_service.replies)
    assert any(reply["message"] == "Updated manual reply" for reply in instagram_service.replies)

    async with session_factory() as session:
        old_answer = await session.get(QuestionAnswer, old_answer_id)
        assert old_answer.is_deleted is True
        assert old_answer.reply_status == "deleted"

        result = await session.execute(
            select(QuestionAnswer).where(
                QuestionAnswer.comment_id == "comment_patch_answer",
                QuestionAnswer.is_deleted.is_(False),
            )
        )
        new_answer = result.scalar_one()
        assert new_answer.answer == "Updated manual reply"
        assert new_answer.answer_confidence == 1.0
        assert new_answer.answer_quality_score == 100
        assert new_answer.reply_id != "reply-original-999"


@pytest.mark.asyncio
async def test_put_answer_creates_manual_reply(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_put_answer",
            permalink="https://instagram.com/p/media_put_answer",
            media_type="IMAGE",
            media_url="https://cdn.test/media_put_answer.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.flush()

        comment = InstagramComment(
            id="comment_put_answer",
            media_id=media.id,
            user_id="user_put",
            username="user_put",
            text="Need manual answer",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.put(
        "/api/v1/comments/comment_put_answer/answers",
        json={"answer": "Manual answer"},
        headers=auth_headers(integration_environment),
    )

    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["answer"] == "Manual answer"
    assert payload["confidence"] == 100
    assert payload["quality_score"] == 100
    assert payload["reply_sent"] is True

    assert any(reply["message"] == "Manual answer" for reply in instagram_service.replies)

    async with session_factory() as session:
        result = await session.execute(
            select(QuestionAnswer).where(
                QuestionAnswer.comment_id == "comment_put_answer",
                QuestionAnswer.is_deleted.is_(False),
            )
        )
        new_answer = result.scalar_one()
        assert new_answer.answer == "Manual answer"
        assert new_answer.answer_confidence == 1.0
        assert new_answer.answer_quality_score == 100


@pytest.mark.asyncio
async def test_delete_answer_instagram_api_failure(integration_environment):
    """Test deletion fails with 502 when Instagram API returns error."""
    from unittest.mock import AsyncMock

    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    # Setup: Create answer with reply_id
    async with session_factory() as session:
        media = Media(
            id="media_api_fail",
            permalink="https://instagram.com/p/media_api_fail",
            media_type="IMAGE",
            media_url="https://cdn.test/media_api_fail.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_api_fail",
            media_id=media.id,
            user_id="user_api_fail",
            username="user_api_fail",
            text="Question",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.flush()

        classification = CommentClassification(
            comment_id=comment.id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        session.add(classification)

        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Answer text",
            reply_sent=True,
            reply_status="sent",
            reply_id="reply_api_fail_123",
        )
        session.add(answer)
        await session.commit()
        answer_id = answer.id

    # Mock Instagram service to return failure
    original_delete = instagram_service.delete_comment_reply
    instagram_service.delete_comment_reply = AsyncMock(
        return_value={"success": False, "error": "Instagram API error", "status_code": 500}
    )

    try:
        # Action: Attempt to delete
        response = await client.delete(
            f"/api/v1/answers/{answer_id}",
            headers=auth_headers(integration_environment),
        )

        # Verify error response
        assert response.status_code == 502
        data = response.json()
        # Success is False when error is present
        assert data["meta"]["error"]["code"] == 5004
        assert "Failed to delete reply on Instagram" in data["meta"]["error"]["message"]

        # Verify answer unchanged in DB
        async with session_factory() as session:
            unchanged_answer = await session.get(QuestionAnswer, answer_id)
            assert unchanged_answer.reply_sent is True
            assert unchanged_answer.reply_status == "sent"
            assert unchanged_answer.reply_id == "reply_api_fail_123"

    finally:
        # Restore original method
        instagram_service.delete_comment_reply = original_delete


@pytest.mark.asyncio
async def test_delete_answer_not_found(integration_environment):
    """Test deletion fails with 404 when answer doesn't exist."""
    client: AsyncClient = integration_environment["client"]

    # Action: Attempt to delete non-existent answer
    response = await client.delete(
        "/api/v1/answers/99999",
        headers=auth_headers(integration_environment),
    )

    # Verify error response
    assert response.status_code == 404
    data = response.json()
    # Success is False when error is present
    assert data["meta"]["error"]["code"] == 4042  # Answer not found


@pytest.mark.asyncio
async def test_delete_answer_multiple_attempts(integration_environment):
    """Test that a second deletion attempt fails once Instagram reply is removed."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    # Setup: Create answer
    async with session_factory() as session:
        media = Media(
            id="media_concurrent_del",
            permalink="https://instagram.com/p/media_concurrent_del",
            media_type="IMAGE",
            media_url="https://cdn.test/media_concurrent_del.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_concurrent_del",
            media_id=media.id,
            user_id="user_concurrent",
            username="user_concurrent",
            text="Question",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.flush()

        classification = CommentClassification(
            comment_id=comment.id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        session.add(classification)

        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Answer",
            reply_sent=True,
            reply_status="sent",
            reply_id="reply_concurrent_123",
        )
        session.add(answer)
        await session.commit()
        answer_id = answer.id

    # Simulate reply in Instagram
    instagram_service.replies.append({
        "comment_id": "comment_concurrent_del",
        "reply_id": "reply_concurrent_123",
        "message": "Answer",
    })

    # First deletion succeeds
    first_response = await client.delete(
        f"/api/v1/answers/{answer_id}",
        headers=auth_headers(integration_environment),
    )
    assert first_response.status_code == 200

    # Second deletion attempt returns 404 because the answer is now soft deleted
    second_response = await client.delete(
        f"/api/v1/answers/{answer_id}",
        headers=auth_headers(integration_environment),
    )
    assert second_response.status_code == 404
    error_payload = second_response.json()
    assert error_payload["meta"]["error"]["code"] == 4042

    # Verify final state
    async with session_factory() as session:
        final_answer = await session.get(QuestionAnswer, answer_id)
        assert final_answer.reply_sent is False
        assert final_answer.reply_status == "deleted"
        assert final_answer.is_deleted is True

    # Instagram reply should be gone after the successful delete
    assert len([r for r in instagram_service.replies if r.get("reply_id") == "reply_concurrent_123"]) == 0


@pytest.mark.asyncio
async def test_delete_answer_with_pending_status(integration_environment):
    """Test deletion of answer with pending reply status."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    # Setup: Create answer with pending status
    async with session_factory() as session:
        media = Media(
            id="media_pending_del",
            permalink="https://instagram.com/p/media_pending_del",
            media_type="IMAGE",
            media_url="https://cdn.test/media_pending_del.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_pending_del",
            media_id=media.id,
            user_id="user_pending",
            username="user_pending",
            text="Question",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.flush()

        classification = CommentClassification(
            comment_id=comment.id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        session.add(classification)

        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Answer",
            reply_sent=False,
            reply_status="pending",  # Pending status
            reply_id="reply_pending_123",  # Has reply_id
        )
        session.add(answer)
        await session.commit()
        answer_id = answer.id

    # Simulate reply in Instagram
    instagram_service.replies.append({
        "comment_id": "comment_pending_del",
        "reply_id": "reply_pending_123",
        "message": "Answer",
    })

    # Action: Delete answer
    response = await client.delete(
        f"/api/v1/answers/{answer_id}",
        headers=auth_headers(integration_environment),
    )

    # Verify success (deletion works regardless of pending status)
    assert response.status_code == 200

    # Verify state transition: pending → deleted
    async with session_factory() as session:
        deleted_answer = await session.get(QuestionAnswer, answer_id)
        assert deleted_answer.reply_sent is False
        assert deleted_answer.reply_status == "deleted"

    # Verify Instagram reply removed
    assert len(instagram_service.replies) == 0


@pytest.mark.asyncio
async def test_delete_answer_persists_in_database(integration_environment):
    """Test that deleted answer is not removed from database."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    # Setup
    async with session_factory() as session:
        media = Media(
            id="media_persist",
            permalink="https://instagram.com/p/media_persist",
            media_type="IMAGE",
            media_url="https://cdn.test/media_persist.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_persist",
            media_id=media.id,
            user_id="user_persist",
            username="user_persist",
            text="Question with history",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.flush()

        classification = CommentClassification(
            comment_id=comment.id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        session.add(classification)

        original_sent_at = now_db_utc()
        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Important historical answer",
            reply_sent=True,
            reply_status="sent",
            reply_id="reply_persist_123",
            reply_sent_at=original_sent_at,
            reply_response={"message_id": "msg_123"},
        )
        session.add(answer)
        await session.commit()
        answer_id = answer.id

    instagram_service.replies.append({
        "comment_id": "comment_persist",
        "reply_id": "reply_persist_123",
        "message": "Important historical answer",
    })

    # Action: Delete
    response = await client.delete(
        f"/api/v1/answers/{answer_id}",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200

    # Verify: Answer still exists with all original data preserved
    async with session_factory() as session:
        answer = await session.get(QuestionAnswer, answer_id)
        assert answer is not None
        assert answer.id == answer_id
        assert answer.comment_id == "comment_persist"
        assert answer.answer == "Important historical answer"
        assert answer.reply_id == "reply_persist_123"  # Preserved
        assert answer.reply_sent_at == original_sent_at  # Preserved
        assert answer.reply_response == {"message_id": "msg_123"}  # Preserved
        # Only status fields changed
        assert answer.reply_sent is False
        assert answer.reply_status == "deleted"
        assert answer.reply_error is None


@pytest.mark.asyncio
async def test_delete_answer_isolation_between_comments(integration_environment):
    """Test that deleting one answer doesn't affect other comments' answers."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    # Setup: Two separate comments, each with their own answer
    async with session_factory() as session:
        media = Media(
            id="media_multi_answer",
            permalink="https://instagram.com/p/media_multi_answer",
            media_type="IMAGE",
            media_url="https://cdn.test/media_multi_answer.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        # First comment with answer (will be deleted)
        comment1 = InstagramComment(
            id="comment_multi_1",
            media_id=media.id,
            user_id="user_multi_1",
            username="user_multi_1",
            text="Question 1",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment1)
        await session.flush()

        classification1 = CommentClassification(
            comment_id=comment1.id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        session.add(classification1)

        answer1 = QuestionAnswer(
            comment_id=comment1.id,
            answer="First answer",
            reply_sent=True,
            reply_status="sent",
            reply_id="reply_multi_1",
        )
        session.add(answer1)

        # Second comment with answer (should remain unchanged)
        comment2 = InstagramComment(
            id="comment_multi_2",
            media_id=media.id,
            user_id="user_multi_2",
            username="user_multi_2",
            text="Question 2",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment2)
        await session.flush()

        classification2 = CommentClassification(
            comment_id=comment2.id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        session.add(classification2)

        answer2 = QuestionAnswer(
            comment_id=comment2.id,
            answer="Second answer",
            reply_sent=True,
            reply_status="sent",
            reply_id="reply_multi_2",
        )
        session.add(answer2)
        await session.commit()
        answer1_id = answer1.id
        answer2_id = answer2.id

    # Simulate both replies in Instagram
    instagram_service.replies.extend([
        {"comment_id": "comment_multi_1", "reply_id": "reply_multi_1", "message": "First answer"},
        {"comment_id": "comment_multi_2", "reply_id": "reply_multi_2", "message": "Second answer"},
    ])

    # Action: Delete only first answer
    response = await client.delete(
        f"/api/v1/answers/{answer1_id}",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200

    # Verify: First answer deleted, second unchanged
    async with session_factory() as session:
        answer1_after = await session.get(QuestionAnswer, answer1_id)
        assert answer1_after.reply_sent is False
        assert answer1_after.reply_status == "deleted"

        answer2_after = await session.get(QuestionAnswer, answer2_id)
        assert answer2_after.reply_sent is True
        assert answer2_after.reply_status == "sent"

    # Verify: Only first reply deleted from Instagram
    assert len(instagram_service.replies) == 1
    assert instagram_service.replies[0]["reply_id"] == "reply_multi_2"
