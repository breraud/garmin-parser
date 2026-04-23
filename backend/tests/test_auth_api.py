from collections.abc import AsyncIterator
from unittest.mock import Mock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes_exports import get_garmin_client_registry_dependency
from app.core.auth import token_manager
from app.garmin.exceptions import GarminAuthenticationError, GarminRateLimitError
from app.garmin.registry import GarminClientRegistry
from app.main import app


class FakeGarminClient:
    def __init__(self) -> None:
        self.login = Mock(
            return_value=type("Session", (), {"authenticated": True, "mfa_required": False})()
        )


class FakeGarminClientRegistry:
    def __init__(self, garmin_client: FakeGarminClient) -> None:
        self.garmin_client = garmin_client
        self.get_client = Mock(return_value=garmin_client)
        self.logout = Mock(return_value=None)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def override_garmin_registry(registry: FakeGarminClientRegistry) -> None:
    async def dependency_override() -> GarminClientRegistry:
        return registry  # type: ignore[return-value]

    app.dependency_overrides[get_garmin_client_registry_dependency] = dependency_override


def clear_overrides() -> None:
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_login_route_authenticates_and_returns_success(
    api_client: AsyncClient,
) -> None:
    garmin_client = FakeGarminClient()
    registry = FakeGarminClientRegistry(garmin_client)
    override_garmin_registry(registry)

    try:
        response = await api_client.post(
            "/api/auth/login",
            json={"email": "runner@example.com", "password": "secret"},
        )
    finally:
        clear_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert isinstance(payload["access_token"], str)
    assert token_manager.verify_access_token(payload["access_token"]).email_hash
    garmin_client.login.assert_called_once_with("runner@example.com", "secret")
    registry.get_client.assert_called_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exception", "expected_status"),
    [
        (GarminAuthenticationError("bad credentials"), 401),
        (GarminRateLimitError("rate limited"), 429),
    ],
)
async def test_login_route_maps_garmin_errors_to_http(
    api_client: AsyncClient,
    exception: Exception,
    expected_status: int,
) -> None:
    garmin_client = FakeGarminClient()
    garmin_client.login.side_effect = exception
    registry = FakeGarminClientRegistry(garmin_client)
    override_garmin_registry(registry)

    try:
        response = await api_client.post(
            "/api/auth/login",
            json={"email": "runner@example.com", "password": "secret"},
        )
    finally:
        clear_overrides()

    assert response.status_code == expected_status
    assert response.json()["detail"]


@pytest.mark.anyio
async def test_logout_route_revokes_authenticated_session(
    api_client: AsyncClient,
) -> None:
    garmin_client = FakeGarminClient()
    registry = FakeGarminClientRegistry(garmin_client)
    override_garmin_registry(registry)
    token = token_manager.create_access_token("runner@example.com")

    try:
        response = await api_client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        clear_overrides()

    assert response.status_code == 200
    assert response.json() == {"status": "logged_out", "message": "Garmin session cleared."}
    registry.logout.assert_called_once_with(
        token_manager.verify_access_token(token).email_hash,
    )


@pytest.mark.anyio
async def test_logout_route_rejects_missing_bearer_token(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post("/api/auth/logout")

    assert response.status_code == 401
