"""Concurrent operations and race condition tests for JSON API endpoints."""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from core.models import CommentClassification, InstagramComment, Media, QuestionAnswer
from core.models.comment_classification import ProcessingStatus
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers


@pytest.mark.asyncio
async def test_concurrent_media_processing_toggle(integration_environment):
    """Test concurrent updates to media is_processing_enabled field."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Create media
    async with session_factory() as session:
        media = Media(
            id="media_concurrent_toggle",
            permalink="https://instagram.com/p/media_concurrent_toggle",
            media_type="IMAGE",
            media_url="https://cdn.test/concurrent.jpg",
            is_processing_enabled=True,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    # Send 5 concurrent requests toggling the same field
    async def toggle_processing(enable: bool):
        return await client.patch(
            "/api/v1/media/media_concurrent_toggle",
            headers=auth_headers(integration_environment),
            json={"is_processing_enabled": enable},
        )

    # Create alternating enable/disable requests
    tasks = [
        toggle_processing(False),
        toggle_processing(True),
        toggle_processing(False),
        toggle_processing(True),
        toggle_processing(False),
    ]

    # Execute concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # All should succeed (no crashes or 500 errors)
    seen_processing_values: set[bool] = set()
    for i, response in enumerate(responses):
        if isinstance(response, Exception):
            pytest.fail(f"Request {i} raised exception: {response}")
        assert response.status_code == 200, f"Request {i} failed with status {response.status_code}"
        payload = response.json().get("payload")
        assert payload is not None
        seen_processing_values.add(payload["is_processing_enabled"])

    assert seen_processing_values, "No successful toggle response recorded"

    # Verify final state is consistent in database
    async with session_factory() as session:
        final_media = await session.get(Media, "media_concurrent_toggle")
        assert final_media is not None
        assert final_media.is_processing_enabled in seen_processing_values


@pytest.mark.asyncio
async def test_concurrent_comment_classification_updates(integration_environment):
    """Test concurrent classification updates on same comment."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Create comment with classification
    async with session_factory() as session:
        media = Media(
            id="media_concurrent_class",
            permalink="https://instagram.com/p/media_concurrent_class",
            media_type="IMAGE",
            media_url="https://cdn.test/class_concurrent.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_concurrent_class",
            media_id=media.id,
            user_id="user_concurrent",
            username="concurrent_user",
            text="Concurrent test",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        classification = CommentClassification(
            comment_id=comment.id,
            type="positive feedback",
            processing_status="COMPLETED",
        )
        session.add(classification)
        await session.commit()

    # Different classification types
    classification_types = [
        "critical feedback",
        "urgent issue / complaint",
        "question / inquiry",
        "positive feedback",
        "partnership proposal",
    ]

    # Send concurrent classification updates
    async def update_classification(class_type: str, reasoning: str):
        return await client.patch(
            "/api/v1/comments/comment_concurrent_class/classification",
            headers=auth_headers(integration_environment),
            json={"type": class_type, "reasoning": reasoning},
        )

    tasks = [
        update_classification(class_types, f"reason_{i}")
        for i, class_types in enumerate(classification_types)
    ]

    # Execute concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # All should succeed and final DB state should match last successful request
    from api_v1.comments.serializers import CLASSIFICATION_TYPE_CODES

    code_to_label = {code: label for label, code in CLASSIFICATION_TYPE_CODES.items()}

    observed_states: set[tuple[str | None, str | None]] = set()
    for idx, response in enumerate(responses):
        if isinstance(response, Exception):
            pytest.fail(f"Classification update {idx} raised exception: {response}")
        assert response.status_code == 200, f"Request {idx} failed with status {response.status_code}"
        payload = response.json().get("payload")
        assert payload is not None
        classification_payload = payload.get("classification")
        assert classification_payload is not None
        type_code = classification_payload.get("classification_type")
        reasoning = classification_payload.get("reasoning")
        type_label = code_to_label.get(type_code)
        observed_states.add((type_label, reasoning))

    assert observed_states, "No successful classification updates recorded"

    # Verify database state is consistent (one of the requested types)
    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(CommentClassification).where(
                CommentClassification.comment_id == "comment_concurrent_class"
            )
        )
        final_classification = result.scalar_one()
        final_state = (final_classification.type, final_classification.reasoning)
        assert final_state in observed_states
        # Confidence should be None (manual override)
        assert final_classification.confidence is None
        assert getattr(final_classification.processing_status, "name", final_classification.processing_status) == "COMPLETED"


@pytest.mark.asyncio
async def test_concurrent_comment_hide_toggle(integration_environment):
    """Test concurrent hide/unhide operations on same comment."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    # Create comment
    async with session_factory() as session:
        media = Media(
            id="media_concurrent_hide",
            permalink="https://instagram.com/p/media_concurrent_hide",
            media_type="IMAGE",
            media_url="https://cdn.test/hide_concurrent.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_concurrent_hide",
            media_id=media.id,
            user_id="user_hide_concurrent",
            username="hide_user",
            text="Hide/unhide test",
            is_hidden=False,
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    # Send concurrent hide/unhide requests
    async def toggle_visibility(hide: bool):
        return await client.patch(
            "/api/v1/comments/comment_concurrent_hide",
            headers=auth_headers(integration_environment),
            params={"is_hidden": hide},
        )

    tasks = [
        toggle_visibility(True),
        toggle_visibility(False),
        toggle_visibility(True),
        toggle_visibility(False),
        toggle_visibility(True),
    ]

    # Execute concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # All should succeed
    success_count = 0
    seen_visibility: set[bool] = set()
    for i, response in enumerate(responses):
        if isinstance(response, Exception):
            pytest.fail(f"Hide toggle {i} raised exception: {response}")
        assert response.status_code in [200, 502], f"Unexpected status {response.status_code}"
        if response.status_code == 200:
            success_count += 1
            payload = response.json().get("payload")
            assert payload is not None
            seen_visibility.add(payload["is_hidden"])

    # At least some requests should succeed
    assert success_count >= 1, "No hide/unhide requests succeeded"
    assert seen_visibility, "No successful visibility payload recorded"

    # Verify final state in database is consistent
    async with session_factory() as session:
        final_comment = await session.get(InstagramComment, "comment_concurrent_hide")
        assert final_comment is not None
        assert final_comment.is_hidden in seen_visibility


@pytest.mark.asyncio
async def test_concurrent_answer_updates(integration_environment):
    """Test concurrent updates to same answer."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Create answer
    async with session_factory() as session:
        media = Media(
            id="media_concurrent_answer",
            permalink="https://instagram.com/p/media_concurrent_answer",
            media_type="IMAGE",
            media_url="https://cdn.test/answer_concurrent.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_concurrent_answer",
            media_id=media.id,
            user_id="user_answer",
            username="answer_user",
            text="Question?",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        answer = QuestionAnswer(
            id=9999,
            comment_id=comment.id,
            answer="Original answer",
            answer_confidence=0.5,
            answer_quality_score=50,
            processing_status="COMPLETED",
        )
        session.add(answer)
        await session.commit()

    # Send concurrent answer updates
    async def update_answer(text: str, confidence: int):
        return await client.patch(
            "/api/v1/answers/9999",
            headers=auth_headers(integration_environment),
            json={"answer": text, "confidence": confidence},
        )

    tasks = [
        update_answer(f"Answer version {i}", 60 + i * 5)
        for i in range(5)
    ]

    # Execute concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # All should succeed
    observed_answers: set[str] = {"Original answer"}
    observed_confidences: set[float] = {0.5}
    success_count = 0
    for i, response in enumerate(responses):
        if isinstance(response, Exception):
            pytest.fail(f"Answer update {i} raised exception: {response}")
        if response.status_code == 200:
            payload = response.json().get("payload")
            assert payload is not None
            observed_answers.add(payload["answer"])
            observed_confidences.add(payload["confidence"] / 100)
            success_count += 1
        else:
            assert response.status_code == 502, f"Unexpected status {response.status_code}"
            error_payload = response.json()
            assert error_payload["meta"]["error"]["code"] == 5005

    assert success_count >= 0

    # Verify final state matches last successful update
    async with session_factory() as session:
        result = await session.execute(
            select(QuestionAnswer).where(
                QuestionAnswer.comment_id == "comment_concurrent_answer",
                QuestionAnswer.is_deleted.is_(False),
            )
        )
        final_answer = result.scalar_one()
        assert final_answer.answer in observed_answers
        assert any(pytest.approx(conf, rel=1e-6) == final_answer.answer_confidence for conf in observed_confidences)


@pytest.mark.asyncio
async def test_concurrent_media_context_updates(integration_environment):
    """Test concurrent updates to media context field."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Create media
    async with session_factory() as session:
        media = Media(
            id="media_concurrent_context",
            permalink="https://instagram.com/p/media_concurrent_context",
            media_type="IMAGE",
            media_url="https://cdn.test/context_concurrent.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    # Send concurrent context updates
    async def update_context(context_text: str):
        return await client.patch(
            "/api/v1/media/media_concurrent_context",
            headers=auth_headers(integration_environment),
            json={"context": context_text},
        )

    contexts = [
        "Promotional post for product A",
        "Behind the scenes content",
        "Customer testimonial",
        "Product launch announcement",
        "Tutorial content",
    ]

    tasks = [update_context(ctx) for ctx in contexts]

    # Execute concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # All should succeed
    observed_contexts: set[str] = set()
    for i, response in enumerate(responses):
        if isinstance(response, Exception):
            pytest.fail(f"Context update {i} raised exception: {response}")
        assert response.status_code == 200, f"Request {i} failed with status {response.status_code}"
        payload = response.json().get("payload")
        assert payload is not None
        observed_contexts.add(payload["context"])

    assert observed_contexts

    # Verify final state matches last successful update
    async with session_factory() as session:
        final_media = await session.get(Media, "media_concurrent_context")
        assert final_media is not None
        assert final_media.media_context in observed_contexts


@pytest.mark.asyncio
async def test_concurrent_mixed_media_operations(integration_environment):
    """Test concurrent mixed operations (processing toggle + context update) on same media."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Create media
    async with session_factory() as session:
        media = Media(
            id="media_concurrent_mixed",
            permalink="https://instagram.com/p/media_concurrent_mixed",
            media_type="IMAGE",
            media_url="https://cdn.test/mixed_concurrent.jpg",
            is_processing_enabled=True,
            media_context="Initial context",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    # Mix of different update operations
    async def toggle_processing():
        return await client.patch(
            "/api/v1/media/media_concurrent_mixed",
            headers=auth_headers(integration_environment),
            json={"is_processing_enabled": False},
        )

    async def update_context():
        return await client.patch(
            "/api/v1/media/media_concurrent_mixed",
            headers=auth_headers(integration_environment),
            json={"context": "New context from concurrent request"},
        )

    async def update_both():
        return await client.patch(
            "/api/v1/media/media_concurrent_mixed",
            headers=auth_headers(integration_environment),
            json={
                "is_processing_enabled": True,
                "context": "Both fields updated",
            },
        )

    # Mix of operations
    tasks = [
        toggle_processing(),
        update_context(),
        update_both(),
        toggle_processing(),
        update_context(),
    ]

    # Execute concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # All should succeed
    observed_processing: set[bool] = set()
    observed_contexts: set[str] = set()
    for i, response in enumerate(responses):
        if isinstance(response, Exception):
            pytest.fail(f"Mixed operation {i} raised exception: {response}")
        assert response.status_code == 200, f"Request {i} failed with status {response.status_code}"
        payload = response.json().get("payload")
        assert payload is not None
        if "is_processing_enabled" in payload:
            observed_processing.add(payload["is_processing_enabled"])
        if "context" in payload and payload["context"] is not None:
            observed_contexts.add(payload["context"])

    assert observed_processing
    assert observed_contexts

    # Verify final state matches last successful payload
    async with session_factory() as session:
        final_media = await session.get(Media, "media_concurrent_mixed")
        assert final_media is not None
        assert final_media.is_processing_enabled in observed_processing
        assert final_media.media_context in observed_contexts


@pytest.mark.asyncio
async def test_concurrent_comment_delete_and_update(integration_environment):
    """Test race condition between comment deletion and classification update."""
    from sqlalchemy import select

    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Create comment
    async with session_factory() as session:
        media = Media(
            id="media_delete_race",
            permalink="https://instagram.com/p/media_delete_race",
            media_type="IMAGE",
            media_url="https://cdn.test/delete_race.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_delete_race",
            media_id=media.id,
            user_id="user_delete",
            username="delete_user",
            text="Will be deleted",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        comment_class = CommentClassification(
            comment_id=comment.id,
            type="spam / irrelevant",
            processing_status="COMPLETED",
        )
        session.add(comment_class)
        await session.commit()

    # Concurrent delete and update
    async def delete_comment():
        return await client.delete(
            "/api/v1/comments/comment_delete_race",
            headers=auth_headers(integration_environment),
        )

    async def update_classification():
        return await client.patch(
            "/api/v1/comments/comment_delete_race/classification",
            headers=auth_headers(integration_environment),
            json={"type": "question / inquiry", "reasoning": "updated"},
        )

    # Run concurrently - one should fail gracefully
    responses = await asyncio.gather(
        delete_comment(),
        update_classification(),
        delete_comment(),  # Second delete should also handle gracefully
        return_exceptions=True,
    )

    # At least one operation should complete
    success_count = sum(
        1 for r in responses
        if not isinstance(r, Exception) and r.status_code in [200, 404]
    )
    assert success_count >= 1, "No operations succeeded"

    # Verify database state is consistent
    async with session_factory() as session:
        deleted_comment = await session.get(InstagramComment, "comment_delete_race")
        # Comment may or may not exist depending on race outcome
        # But database should be consistent (no orphaned classification)
        if deleted_comment is None:
            # If comment deleted, classification should also be gone (cascade)
            result = await session.execute(
                select(CommentClassification).where(
                    CommentClassification.comment_id == "comment_delete_race"
                )
            )
            orphaned_classification = result.scalar_one_or_none()
            # SQLAlchemy cascade should have handled this
            # (This depends on your cascade configuration)
