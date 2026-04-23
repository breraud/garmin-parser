from collections.abc import AsyncIterator
from unittest.mock import Mock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes_exports import get_garmin_client
from app.core.auth import token_manager
from app.garmin.exceptions import GarminAuthenticationError, GarminRateLimitError
from app.main import app


class FakeGarminClient:
    def __init__(self) -> None:
        self.ensure_authenticated = Mock(return_value=object())
        self.get_activities = Mock(
            return_value=[
                {
                    "activityId": "run-1",
                    "activityName": "Footing vallonne",
                    "startTimeLocal": "2026-04-19 08:30:00",
                    "distance": 10240.0,
                    "activityTypeDTO": {"typeKey": "running"},
                },
                {
                    "activityId": "ride-1",
                    "activityName": "Sortie velo",
                    "startTimeLocal": "2026-04-18 09:00:00",
                    "distance": 40200.0,
                    "activityTypeDTO": {"typeKey": "cycling"},
                },
                {
                    "activityId": "run-2",
                    "activityName": "Seuil",
                    "startTimeLocal": "2026-04-17 18:30:00",
                    "distance": 8000.0,
                    "activityTypeDTO": {"typeKey": "running_walking"},
                },
            ]
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def override_garmin_client(garmin_client: FakeGarminClient) -> None:
    async def dependency_override() -> FakeGarminClient:
        return garmin_client

    app.dependency_overrides[get_garmin_client] = dependency_override


def clear_overrides() -> None:
    app.dependency_overrides.clear()


def auth_headers() -> dict[str, str]:
    token = token_manager.create_access_token("runner@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_recent_activities_returns_only_running_activities(
    api_client: AsyncClient,
) -> None:
    garmin_client = FakeGarminClient()
    override_garmin_client(garmin_client)

    try:
        response = await api_client.get("/api/activities/recent", headers=auth_headers())
    finally:
        clear_overrides()

    assert response.status_code == 200
    assert response.json() == [
        {
            "activity_id": "run-1",
            "date": "2026-04-19",
            "title": "Footing vallonne",
            "distance_km": 10.24,
        },
        {
            "activity_id": "run-2",
            "date": "2026-04-17",
            "title": "Seuil",
            "distance_km": 8.0,
        },
    ]
    garmin_client.ensure_authenticated.assert_called_once_with()
    garmin_client.get_activities.assert_called_once_with(0, 10)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exception", "expected_status"),
    [
        (GarminAuthenticationError("bad credentials"), 401),
        (GarminRateLimitError("rate limited"), 429),
    ],
)
async def test_recent_activities_maps_garmin_errors_to_http(
    api_client: AsyncClient,
    exception: Exception,
    expected_status: int,
) -> None:
    garmin_client = FakeGarminClient()
    garmin_client.ensure_authenticated.side_effect = exception
    override_garmin_client(garmin_client)

    try:
        response = await api_client.get("/api/activities/recent", headers=auth_headers())
    finally:
        clear_overrides()

    assert response.status_code == expected_status
    assert response.json()["detail"]


@pytest.mark.anyio
async def test_recent_activities_requires_bearer_token(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/activities/recent")

    assert response.status_code == 401
