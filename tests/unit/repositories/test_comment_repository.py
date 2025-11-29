"""Fixed CommentRepository tests"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from core.repositories.comment import CommentRepository
from core.models import InstagramComment
from core.utils.time import now_utc


@pytest.mark.unit
@pytest.mark.repository
class TestCommentRepository:
    """Test CommentRepository methods."""

    async def test_create_comment(self, db_session):
        """Test creating a new comment."""
        # Arrange
        repo = CommentRepository(db_session)
        comment_entity = InstagramComment(
            id="comment_123",
            media_id="media_123",
            user_id="user_123",
            username="test_user",
            text="Test comment",
            created_at=now_utc(),
            raw_data={},
        )

        # Act
        comment = await repo.create(comment_entity)

        # Assert
        assert comment.id == "comment_123"
        assert comment.username == "test_user"
        assert comment.text == "Test comment"
        assert comment.media_id == "media_123"
        assert comment.user_id == "user_123"

    async def test_get_comment_by_id(self, db_session, instagram_comment_factory):
        """Test retrieving a comment by ID."""
        # Arrange
        repo = CommentRepository(db_session)
        created_comment = await instagram_comment_factory(comment_id="test_123")

        # Act
        comment = await repo.get_by_id("test_123")

        # Assert
        assert comment is not None
        assert comment.id == "test_123"
        assert comment.username == created_comment.username

    async def test_get_nonexistent_comment_returns_none(self, db_session):
        """Test that getting non-existent comment returns None."""
        # Arrange
        repo = CommentRepository(db_session)

        # Act
        comment = await repo.get_by_id("nonexistent_id")

        # Assert
        assert comment is None

    async def test_update_comment(self, db_session, instagram_comment_factory):
        """Test updating a comment."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory(text="Original text")

        # Act
        comment.text = "Updated text"
        updated = await repo.update(comment)

        # Assert
        assert updated.text == "Updated text"
        assert updated.id == comment.id

    async def test_delete_comment(self, db_session, instagram_comment_factory):
        """Test deleting a comment."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory()

        # Act
        await repo.delete(comment)

        # Assert
        deleted_comment = await repo.get_by_id(comment.id)
        assert deleted_comment is None

    async def test_mark_deleted_with_descendants(self, db_session, instagram_comment_factory):
        """Soft delete should mark comment and descendants as deleted."""
        repo = CommentRepository(db_session)
        parent = await instagram_comment_factory(comment_id="parent_comment")
        child = await instagram_comment_factory(comment_id="child_comment", parent_id=parent.id)
        grandchild = await instagram_comment_factory(comment_id="grandchild_comment", parent_id=child.id)

        affected = await repo.mark_deleted_with_descendants(parent.id)
        await db_session.commit()

        assert affected == 3

        # Repository should no longer return deleted comments
        assert await repo.get_by_id(parent.id) is None
        assert await repo.get_by_id(child.id) is None

        # Raw query verifies flag is set
        parent_row = await db_session.get(InstagramComment, parent.id)
        assert parent_row.is_deleted is True
        child_row = await db_session.get(InstagramComment, child.id)
        assert child_row.is_deleted is True
        grandchild_row = await db_session.get(InstagramComment, grandchild.id)
        assert grandchild_row.is_deleted is True

    async def test_list_for_media_default_includes_deleted(self, db_session, instagram_comment_factory):
        repo = CommentRepository(db_session)
        active = await instagram_comment_factory(media_id="media-list", is_deleted=False)
        deleted = await instagram_comment_factory(media_id="media-list", is_deleted=True)

        results = await repo.list_for_media("media-list", offset=0, limit=10)
        ids = {comment.id for comment in results}
        assert {active.id, deleted.id} <= ids

        without_deleted = await repo.list_for_media(
            "media-list", offset=0, limit=10, include_deleted=False
        )
        ids_without = {comment.id for comment in without_deleted}
        assert active.id in ids_without
        assert deleted.id not in ids_without

    async def test_comment_persistence(self, db_session):
        """Test that created comment persists in database."""
        # Arrange
        repo = CommentRepository(db_session)
        comment_entity = InstagramComment(
            id="persist_test",
            media_id="media_123",
            user_id="user_123",
            username="test",
            text="Persist test",
            created_at=now_utc(),
            raw_data={},
        )

        # Act
        await repo.create(comment_entity)
        await db_session.commit()

        # Verify persistence with fresh query
        result = await db_session.execute(
            select(InstagramComment).where(InstagramComment.id == "persist_test")
        )
        persisted_comment = result.scalar_one_or_none()

        # Assert
        assert persisted_comment is not None
        assert persisted_comment.text == "Persist test"

    async def test_get_with_classification(self, db_session, instagram_comment_factory, classification_factory):
        """Test getting comment with classification eagerly loaded."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory()
        await classification_factory(comment_id=comment.id, classification="positive")

        # Act
        result = await repo.get_with_classification(comment.id)

        # Assert
        assert result is not None
        assert result.id == comment.id
        assert result.classification is not None
        assert result.classification.type == "positive"

    async def test_get_with_answer(self, db_session, instagram_comment_factory, answer_factory):
        """Test getting comment with answer eagerly loaded."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory()
        await answer_factory(comment_id=comment.id, answer_text="Test answer")

        # Act
        result = await repo.get_with_answer(comment.id)

        # Assert
        assert result is not None
        assert result.id == comment.id
        assert result.question_answer is not None
        assert result.question_answer.answer == "Test answer"

    async def test_get_full(self, db_session, instagram_comment_factory, classification_factory, answer_factory, media_factory):
        """Test getting comment with all relationships eagerly loaded."""
        # Arrange
        repo = CommentRepository(db_session)
        media = await media_factory(media_id="media_full_test")
        comment = await instagram_comment_factory(media_id=media.id)
        await classification_factory(comment_id=comment.id, classification="question / inquiry")
        await answer_factory(comment_id=comment.id, answer_text="Full test answer")

        # Act
        result = await repo.get_full(comment.id)

        # Assert
        assert result is not None
        assert result.id == comment.id
        assert result.classification is not None
        assert result.classification.type == "question / inquiry"
        assert result.question_answer is not None
        assert result.question_answer.answer == "Full test answer"
        assert result.media is not None
        assert result.media.id == media.id

    async def test_get_with_classification_no_classification(self, db_session, instagram_comment_factory):
        """Test getting comment with classification when none exists."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory()

        # Act
        result = await repo.get_with_classification(comment.id)

        # Assert
        assert result is not None
        assert result.id == comment.id
        assert result.classification is None

    async def test_list_all_comments(self, db_session, instagram_comment_factory):
        """Test listing all comments."""
        # Arrange
        repo = CommentRepository(db_session)
        await instagram_comment_factory(text="Comment 1")
        await instagram_comment_factory(text="Comment 2")
        await instagram_comment_factory(text="Comment 3")

        # Act
        comments = await repo.get_all()

        # Assert
        assert len(comments) >= 3

    async def test_create_comment_with_parent_id(self, db_session, instagram_comment_factory):
        """Test creating a reply comment with parent_id."""
        # Arrange
        repo = CommentRepository(db_session)
        parent_comment = await instagram_comment_factory(comment_id="parent_123")
        reply_entity = InstagramComment(
            id="reply_123",
            media_id=parent_comment.media_id,
            user_id="user_456",
            username="replier",
            text="This is a reply",
            parent_id=parent_comment.id,
            created_at=now_utc(),
            raw_data={},
        )

        # Act
        reply = await repo.create(reply_entity)

        # Assert
        assert reply.id == "reply_123"
        assert reply.parent_id == parent_comment.id
        assert reply.text == "This is a reply"

    async def test_update_is_hidden_flag(self, db_session, instagram_comment_factory):
        """Test updating is_hidden flag on a comment."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory(is_hidden=False)

        # Act
        comment.is_hidden = True
        updated = await repo.update(comment)

        # Assert
        assert updated.is_hidden is True

    async def test_get_with_answer_no_answer(self, db_session, instagram_comment_factory):
        """Test getting comment with answer when none exists."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory()

        # Act
        result = await repo.get_with_answer(comment.id)

        # Assert
        assert result is not None
        assert result.id == comment.id
        assert result.question_answer is None

    async def test_create_comment_with_conversation_id(self, db_session):
        """Test creating comment with conversation ID."""
        # Arrange
        repo = CommentRepository(db_session)
        comment_entity = InstagramComment(
            id="conv_comment_123",
            media_id="media_123",
            user_id="user_123",
            username="test",
            text="Part of conversation",
            conversation_id="conversation_abc",
            created_at=now_utc(),
            raw_data={},
        )

        # Act
        comment = await repo.create(comment_entity)

        # Assert
        assert comment.conversation_id == "conversation_abc"

    async def test_exists_method(self, db_session, instagram_comment_factory):
        """Test checking if comment exists."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory()

        # Act
        exists = await repo.exists(comment.id)
        not_exists = await repo.exists("nonexistent_id")

        # Assert
        assert exists is True
        assert not_exists is False

    async def test_get_with_classification_with_empty_id(self, db_session):
        """Test get_with_classification with empty string ID."""
        # Arrange
        repo = CommentRepository(db_session)

        # Act
        result = await repo.get_with_classification("")

        # Assert
        assert result is None

    async def test_get_full_nonexistent_comment(self, db_session):
        """Test get_full with nonexistent comment ID."""
        # Arrange
        repo = CommentRepository(db_session)

        # Act
        result = await repo.get_full("nonexistent_id")

        # Assert
        assert result is None

    async def test_comment_with_very_long_text(self, db_session):
        """Test creating comment with very long text."""
        # Arrange
        repo = CommentRepository(db_session)
        long_text = "a" * 5000
        comment_entity = InstagramComment(
            id="long_text_comment",
            media_id="media_123",
            user_id="user_123",
            username="test",
            text=long_text,
            created_at=now_utc(),
            raw_data={},
        )

        # Act
        comment = await repo.create(comment_entity)

        # Assert
        assert comment.text == long_text
        assert len(comment.text) == 5000
