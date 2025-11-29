# Service Layer Tests

Unit tests for all service classes. Each service has its own test file.

## Files:

- `test_classification_service.py` - CommentClassificationService (✅ Complete)
- `test_answer_service.py` - QuestionAnswerService (✅ Complete)
- `test_instagram_service.py` - InstagramGraphAPIService (✅ Complete)
- `test_telegram_service.py` - TelegramAlertService (⏳ TODO)
- `test_embedding_service.py` - EmbeddingService (⏳ TODO)
- `test_s3_service.py` - S3Service (⏳ TODO)
- `test_media_service.py` - MediaService (⏳ TODO)
- `test_media_analysis_service.py` - MediaAnalysisService (⏳ TODO)
- `test_document_processing_service.py` - DocumentProcessingService (⏳ TODO)
- `test_document_context_service.py` - DocumentContextService (⏳ TODO)

## Running Tests:

```bash
# Run all service tests
pytest tests/unit/services/ -v

# Run specific service tests
pytest tests/unit/services/test_instagram_service.py -v

# Run with coverage
pytest tests/unit/services/ --cov=src/core/services --cov-report=term-missing
```
