import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.models import CommentClassification, InstagramComment, Media, QuestionAnswer
from core.models.comment_classification import ProcessingStatus
from core.repositories.answer import AnswerRepository
from core.use_cases.replace_answer import ReplaceAnswerUseCase, ReplaceAnswerError
from core.utils.time import now_db_utc


class StubInstagramService:
    def __init__(self) -> None:
        self.deleted = []
        self.sent = []
        self.fail_delete = False
        self.fail_send = False

    async def delete_comment_reply(self, reply_id: str):
        if self.fail_delete:
            return {"success": False, "error": "fail"}
        self.deleted.append(reply_id)
        return {"success": True}

    async def send_reply_to_comment(self, comment_id: str, message: str):
        if self.fail_send:
            return {"success": False, "error": "fail"}
        reply_id = f"reply-{comment_id}-new"
        payload = {"comment_id": comment_id, "message": message, "reply_id": reply_id}
        self.sent.append(payload)
        return {"success": True, "reply_id": reply_id, "response": payload}


@pytest.mark.asyncio
async def test_replace_answer_success(db_session):
    instagram = StubInstagramService()
    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    async with session_factory() as session:
        media = Media(
            id="media_replace",
            permalink="https://instagram.com/p/media_replace",
            media_type="IMAGE",
            media_url="https://cdn.test/media_replace.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_replace",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Original question",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        session.add(
            CommentClassification(
                comment_id=comment.id,
                processing_status=ProcessingStatus.COMPLETED,
            )
        )
        original_started = now_db_utc()
        original_completed = now_db_utc()
        original_sent_at = now_db_utc()
        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Bot reply",
            answer_confidence=0.5,
            answer_quality_score=55,
            reply_sent=True,
            reply_status="sent",
            reply_id="reply-original",
            reply_sent_at=original_sent_at,
            processing_started_at=original_started,
            processing_completed_at=original_completed,
        )
        session.add(answer)
        await session.commit()
        answer_id = answer.id

    async with session_factory() as session:
        use_case = ReplaceAnswerUseCase(
            session=session,
            answer_repository_factory=lambda session=None, **_: AnswerRepository(session),
            instagram_service=instagram,
        )

        new_answer = await use_case.execute(
            answer_id=answer_id,
            new_answer_text="Manual override reply",
            quality_score=92,
        )

        assert new_answer.comment_id == "comment_replace"
        assert new_answer.answer == "Manual override reply"
        assert new_answer.answer_confidence == 1.0
        assert new_answer.answer_quality_score == 100
        assert new_answer.reply_sent is True
        assert new_answer.is_deleted is False
        assert new_answer.processing_started_at is None
        assert new_answer.processing_completed_at is None

    assert instagram.deleted == ["reply-original"]
    assert instagram.sent[-1]["message"] == "Manual override reply"

    async with session_factory() as session:
        original = await session.get(QuestionAnswer, answer_id)
        assert original.is_deleted is True
        assert original.reply_status == "deleted"
        assert original.reply_sent_at == original_sent_at
        assert original.processing_started_at == original_started
        assert original.processing_completed_at == original_completed


@pytest.mark.asyncio
async def test_replace_answer_delete_failure_raises(db_session):
    instagram = StubInstagramService()
    instagram.fail_delete = True
    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    async with session_factory() as session:
        media = Media(
            id="media_replace_fail",
            permalink="https://instagram.com/p/media_replace_fail",
            media_type="IMAGE",
            media_url="https://cdn.test/media_replace_fail.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_replace_fail",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Original question",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Bot reply",
            reply_sent=True,
            reply_status="sent",
            reply_id="reply-fail",
        )
        session.add(answer)
        await session.commit()
        answer_id = answer.id

    async with session_factory() as session:
        use_case = ReplaceAnswerUseCase(
            session=session,
            answer_repository_factory=lambda session=None, **_: AnswerRepository(session),
            instagram_service=instagram,
        )

        with pytest.raises(ReplaceAnswerError):
            await use_case.execute(
                answer_id=answer_id,
                new_answer_text="Manual override reply",
                quality_score=80,
            )

    # Verify original answer unchanged in DB
    async with session_factory() as session:
        original = await session.get(QuestionAnswer, answer_id)
        assert original.is_deleted is False
        assert original.reply_status == "sent"
        assert original.reply_id == "reply-fail"
