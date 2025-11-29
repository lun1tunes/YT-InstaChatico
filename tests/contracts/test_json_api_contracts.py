import json
from pathlib import Path

import pytest

from api_v1.comments import schemas as comment_schemas


CONTRACT_PATH = Path(__file__).with_name("json_api_fields.json")

MODEL_REGISTRY = {
    "MediaDTO": comment_schemas.MediaDTO,
    "ClassificationDTO": comment_schemas.ClassificationDTO,
    "AnswerDTO": comment_schemas.AnswerDTO,
    "CommentDTO": comment_schemas.CommentDTO,
    "SimpleMeta": comment_schemas.SimpleMeta,
    "PaginationMeta": comment_schemas.PaginationMeta,
    "MediaResponse": comment_schemas.MediaResponse,
    "MediaListResponse": comment_schemas.MediaListResponse,
    "MediaQuickStats": comment_schemas.MediaQuickStats,
    "CommentResponse": comment_schemas.CommentResponse,
    "CommentListResponse": comment_schemas.CommentListResponse,
    "AnswerResponse": comment_schemas.AnswerResponse,
    "AnswerListResponse": comment_schemas.AnswerListResponse,
    "ClassificationTypesResponse": comment_schemas.ClassificationTypesResponse,
    "ClassificationTypeDTO": comment_schemas.ClassificationTypeDTO,
    "ErrorDetail": comment_schemas.ErrorDetail,
}


@pytest.mark.parametrize("model_name, expected_fields", json.loads(CONTRACT_PATH.read_text()).items())
def test_json_api_schema_fields(model_name: str, expected_fields: list[str]):
    assert model_name in MODEL_REGISTRY, f"Model {model_name} missing from registry"
    model = MODEL_REGISTRY[model_name]
    actual_fields = list(model.model_fields.keys())
    assert actual_fields == expected_fields
