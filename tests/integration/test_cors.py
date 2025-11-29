import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cors_preflight_request_allowed(integration_environment):
    client: AsyncClient = integration_environment["client"]

    response = await client.options(
        "/api/v1/media",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )

    assert response.status_code in (200, 204)
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin in {"*", "http://localhost:5173"}
    allow_methods = response.headers.get("access-control-allow-methods")
    assert allow_methods is not None
    assert "GET" in allow_methods or allow_methods == "*"
