"""
Unit tests for FastAPI dependency injection functions.

Tests cover:
- Repository dependency providers
- Use case dependency providers
- Service dependency providers
- Generic dependency factory function
- Container integration
- Session injection
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from core.dependencies import (
    # Repository dependencies
    get_comment_repository,
    get_answer_repository,
    # Use case dependencies
    get_classify_comment_use_case,
    get_generate_answer_use_case,
    get_send_reply_use_case,
    get_hide_comment_use_case,
    get_process_webhook_comment_use_case,
    get_send_telegram_notification_use_case,
    get_process_media_use_case,
    get_analyze_media_use_case,
    get_process_document_use_case,
    get_test_comment_processing_use_case,
    create_use_case_dependency,
    # Infrastructure dependencies
    get_task_queue,
    get_s3_service,
    get_document_processing_service,
    get_document_context_service,
)
from core.repositories.comment import CommentRepository
from core.repositories.answer import AnswerRepository


@pytest.mark.unit
class TestRepositoryDependencies:
    """Test repository dependency provider functions."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock AsyncSession."""
        return MagicMock()

    def test_get_comment_repository(self, mock_session):
        """Test get_comment_repository returns CommentRepository instance."""
        # Act
        repo = get_comment_repository(session=mock_session)

        # Assert
        assert isinstance(repo, CommentRepository)
        assert repo.session is mock_session

    def test_get_answer_repository(self, mock_session):
        """Test get_answer_repository returns AnswerRepository instance."""
        # Act
        repo = get_answer_repository(session=mock_session)

        # Assert
        assert isinstance(repo, AnswerRepository)
        assert repo.session is mock_session


@pytest.mark.unit
class TestUseCaseDependencies:
    """Test use case dependency provider functions."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock AsyncSession."""
        return MagicMock()

    @pytest.fixture
    def mock_container(self):
        """Create a mock Container with all use case methods."""
        container = MagicMock()

        # Mock all use case factory methods
        container.classify_comment_use_case = MagicMock(return_value=MagicMock(name="ClassifyCommentUseCase"))
        container.generate_answer_use_case = MagicMock(return_value=MagicMock(name="GenerateAnswerUseCase"))
        container.send_reply_use_case = MagicMock(return_value=MagicMock(name="SendReplyUseCase"))
        container.hide_comment_use_case = MagicMock(return_value=MagicMock(name="HideCommentUseCase"))
        container.process_webhook_comment_use_case = MagicMock(return_value=MagicMock(name="ProcessWebhookCommentUseCase"))
        container.send_telegram_notification_use_case = MagicMock(return_value=MagicMock(name="SendTelegramNotificationUseCase"))
        container.process_media_use_case = MagicMock(return_value=MagicMock(name="ProcessMediaUseCase"))
        container.analyze_media_use_case = MagicMock(return_value=MagicMock(name="AnalyzeMediaUseCase"))
        container.process_document_use_case = MagicMock(return_value=MagicMock(name="ProcessDocumentUseCase"))
        container.test_comment_processing_use_case = MagicMock(return_value=MagicMock(name="TestCommentProcessingUseCase"))

        return container

    def test_get_classify_comment_use_case(self, mock_session, mock_container):
        """Test get_classify_comment_use_case returns use case from container."""
        # Act
        use_case = get_classify_comment_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.classify_comment_use_case.assert_called_once_with(session=mock_session)

    def test_get_generate_answer_use_case(self, mock_session, mock_container):
        """Test get_generate_answer_use_case returns use case from container."""
        # Act
        use_case = get_generate_answer_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.generate_answer_use_case.assert_called_once_with(session=mock_session)

    def test_get_send_reply_use_case(self, mock_session, mock_container):
        """Test get_send_reply_use_case returns use case from container."""
        # Act
        use_case = get_send_reply_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.send_reply_use_case.assert_called_once_with(session=mock_session)

    def test_get_hide_comment_use_case(self, mock_session, mock_container):
        """Test get_hide_comment_use_case returns use case from container."""
        # Act
        use_case = get_hide_comment_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.hide_comment_use_case.assert_called_once_with(session=mock_session)

    def test_get_process_webhook_comment_use_case(self, mock_session, mock_container):
        """Test get_process_webhook_comment_use_case returns use case from container."""
        # Act
        use_case = get_process_webhook_comment_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.process_webhook_comment_use_case.assert_called_once_with(session=mock_session)

    def test_get_send_telegram_notification_use_case(self, mock_session, mock_container):
        """Test get_send_telegram_notification_use_case returns use case from container."""
        # Act
        use_case = get_send_telegram_notification_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.send_telegram_notification_use_case.assert_called_once_with(session=mock_session)

    def test_get_process_media_use_case(self, mock_session, mock_container):
        """Test get_process_media_use_case returns use case from container."""
        # Act
        use_case = get_process_media_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.process_media_use_case.assert_called_once_with(session=mock_session)

    def test_get_analyze_media_use_case(self, mock_session, mock_container):
        """Test get_analyze_media_use_case returns use case from container."""
        # Act
        use_case = get_analyze_media_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.analyze_media_use_case.assert_called_once_with(session=mock_session)

    def test_get_process_document_use_case(self, mock_session, mock_container):
        """Test get_process_document_use_case returns use case from container."""
        # Act
        use_case = get_process_document_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.process_document_use_case.assert_called_once_with(session=mock_session)

    def test_get_test_comment_processing_use_case(self, mock_session, mock_container):
        """Test get_test_comment_processing_use_case returns use case from container."""
        # Act
        use_case = get_test_comment_processing_use_case(session=mock_session, container=mock_container)

        # Assert
        assert use_case is not None
        mock_container.test_comment_processing_use_case.assert_called_once_with(session=mock_session)


@pytest.mark.unit
class TestCreateUseCaseDependency:
    """Test the generic create_use_case_dependency factory function."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock AsyncSession."""
        return MagicMock()

    @pytest.fixture
    def mock_container(self):
        """Create a mock Container."""
        return MagicMock()

    def test_create_use_case_dependency_basic(self, mock_session, mock_container):
        """Test create_use_case_dependency creates a working dependency function."""
        # Arrange
        mock_use_case = MagicMock(name="CustomUseCase")

        def use_case_factory(container, session):
            return mock_use_case

        # Act
        dependency_func = create_use_case_dependency(use_case_factory)
        result = dependency_func(session=mock_session, container=mock_container)

        # Assert
        assert result is mock_use_case

    def test_create_use_case_dependency_passes_correct_arguments(
        self, mock_session, mock_container
    ):
        """Test that created dependency function passes container and session correctly."""
        # Arrange
        mock_use_case = MagicMock()
        captured_args = {}

        def use_case_factory(container, session):
            captured_args['container'] = container
            captured_args['session'] = session
            return mock_use_case

        # Act
        dependency_func = create_use_case_dependency(use_case_factory)
        dependency_func(session=mock_session, container=mock_container)

        # Assert
        assert captured_args['container'] is mock_container
        assert captured_args['session'] is mock_session

    def test_create_use_case_dependency_with_container_method(
        self, mock_session, mock_container
    ):
        """Test create_use_case_dependency with container factory method."""
        # Arrange
        mock_use_case = MagicMock(name="MyUseCase")
        mock_container.my_use_case = MagicMock(return_value=mock_use_case)

        def use_case_factory(container, session):
            return container.my_use_case(session=session)

        # Act
        dependency_func = create_use_case_dependency(use_case_factory)
        result = dependency_func(session=mock_session, container=mock_container)

        # Assert
        assert result is mock_use_case
        mock_container.my_use_case.assert_called_once_with(session=mock_session)

    def test_create_use_case_dependency_callable_returns_callable(self):
        """Test that create_use_case_dependency returns a callable function."""
        # Arrange
        def use_case_factory(container, session):
            return MagicMock()

        # Act
        dependency_func = create_use_case_dependency(use_case_factory)

        # Assert
        assert callable(dependency_func)


@pytest.mark.unit
class TestInfrastructureDependencies:
    """Test infrastructure service dependency provider functions."""

    @pytest.fixture
    def mock_container(self):
        """Create a mock Container with all infrastructure services."""
        container = MagicMock()

        # Mock infrastructure service factory methods
        container.task_queue = MagicMock(return_value=MagicMock(name="TaskQueue"))
        container.s3_service = MagicMock(return_value=MagicMock(name="S3Service"))
        container.document_processing_service = MagicMock(return_value=MagicMock(name="DocumentProcessingService"))
        container.document_context_service = MagicMock(return_value=MagicMock(name="DocumentContextService"))

        return container

    def test_get_task_queue(self, mock_container):
        """Test get_task_queue returns task queue from container."""
        # Act
        task_queue = get_task_queue(container=mock_container)

        # Assert
        assert task_queue is not None
        mock_container.task_queue.assert_called_once_with()

    def test_get_s3_service(self, mock_container):
        """Test get_s3_service returns S3 service from container."""
        # Act
        s3_service = get_s3_service(container=mock_container)

        # Assert
        assert s3_service is not None
        mock_container.s3_service.assert_called_once_with()

    def test_get_document_processing_service(self, mock_container):
        """Test get_document_processing_service returns service from container."""
        # Act
        service = get_document_processing_service(container=mock_container)

        # Assert
        assert service is not None
        mock_container.document_processing_service.assert_called_once_with()

    def test_get_document_context_service(self, mock_container):
        """Test get_document_context_service returns service from container."""
        # Act
        service = get_document_context_service(container=mock_container)

        # Assert
        assert service is not None
        mock_container.document_context_service.assert_called_once_with()


@pytest.mark.unit
class TestDependencyIntegration:
    """Test integration aspects of dependency functions."""

    def test_all_use_case_dependencies_are_functions(self):
        """Test that all use case dependency getters are callable functions."""
        use_case_deps = [
            get_classify_comment_use_case,
            get_generate_answer_use_case,
            get_send_reply_use_case,
            get_hide_comment_use_case,
            get_process_webhook_comment_use_case,
            get_send_telegram_notification_use_case,
            get_process_media_use_case,
            get_analyze_media_use_case,
            get_process_document_use_case,
            get_test_comment_processing_use_case,
        ]

        for dep_func in use_case_deps:
            assert callable(dep_func), f"{dep_func.__name__} should be callable"

    def test_all_repository_dependencies_are_functions(self):
        """Test that all repository dependency getters are callable functions."""
        repo_deps = [
            get_comment_repository,
            get_answer_repository,
        ]

        for dep_func in repo_deps:
            assert callable(dep_func), f"{dep_func.__name__} should be callable"

    def test_all_infrastructure_dependencies_are_functions(self):
        """Test that all infrastructure dependency getters are callable functions."""
        infra_deps = [
            get_task_queue,
            get_s3_service,
            get_document_processing_service,
            get_document_context_service,
        ]

        for dep_func in infra_deps:
            assert callable(dep_func), f"{dep_func.__name__} should be callable"

    def test_repository_dependencies_have_docstrings(self):
        """Test that repository dependency functions have documentation."""
        assert get_comment_repository.__doc__ is not None
        assert get_answer_repository.__doc__ is not None

    def test_use_case_dependencies_have_docstrings(self):
        """Test that use case dependency functions have documentation."""
        use_case_deps = [
            get_classify_comment_use_case,
            get_generate_answer_use_case,
            get_send_reply_use_case,
        ]

        for dep_func in use_case_deps:
            assert dep_func.__doc__ is not None, f"{dep_func.__name__} should have docstring"

    def test_infrastructure_dependencies_have_docstrings(self):
        """Test that infrastructure dependency functions have documentation."""
        assert get_task_queue.__doc__ is not None
        assert get_s3_service.__doc__ is not None
        assert get_document_processing_service.__doc__ is not None
        assert get_document_context_service.__doc__ is not None
