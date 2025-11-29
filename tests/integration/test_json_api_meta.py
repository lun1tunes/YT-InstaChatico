import pytest
from httpx import AsyncClient

from api_v1.comments.serializers import list_classification_types
from tests.integration.json_api_helpers import auth_headers


@pytest.mark.asyncio
async def test_classification_types_requires_auth(integration_environment):
    """Endpoint should reject requests without valid bearer token."""
    client: AsyncClient = integration_environment["client"]

    response = await client.get("/api/v1/meta/classification-types")

    assert response.status_code == 401
    data = response.json()
    assert data["meta"]["error"]["code"] in (4001, 4002)


@pytest.mark.asyncio
async def test_classification_types_wrong_token(integration_environment):
    """Endpoint should reject requests with incorrect bearer token."""
    client: AsyncClient = integration_environment["client"]

    response = await client.get(
        "/api/v1/meta/classification-types",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["meta"]["error"]["code"] == 4002


@pytest.mark.asyncio
async def test_classification_types_returns_sorted_mapping(integration_environment):
    """Endpoint should return the canonical classification mapping sorted by code."""
    client: AsyncClient = integration_environment["client"]

    response = await client.get(
        "/api/v1/meta/classification-types",
        headers=auth_headers(integration_environment),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["error"] is None

    expected = [
        {"code": code, "label": label}
        for code, label in list_classification_types()
    ]
    assert payload["payload"] == expected
