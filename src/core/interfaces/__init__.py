"""
Service interfaces/protocols for dependency injection.

This module defines abstract protocols that services must implement,
following the Dependency Inversion Principle (DIP).
"""

from .services import (
    IClassificationService,
    IAnswerService,
    IInstagramService,
    IMediaService,
    IMediaAnalysisService,
    IEmbeddingService,
    ITelegramService,
    IS3Service,
    IDocumentProcessingService,
    ITaskQueue,
)

__all__ = [
    "IClassificationService",
    "IAnswerService",
    "IInstagramService",
    "IMediaService",
    "IMediaAnalysisService",
    "IEmbeddingService",
    "ITelegramService",
    "IS3Service",
    "IDocumentProcessingService",
    "ITaskQueue",
]
