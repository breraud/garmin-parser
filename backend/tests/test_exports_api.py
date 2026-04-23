from collections.abc import AsyncIterator
from datetime import date
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes_exports import get_garmin_client, get_markdown_renderer
from app.core.auth import token_manager
from app.garmin.exceptions import (
    GarminActivityNotFoundError,
    GarminAuthenticationError,
    GarminConnectionError,
    GarminRateLimitError,
)
from app.main import app
from app.schemas.internal import ActivitySummary, NormalizedActivity, PhysiologySnapshot


class FakeGarminClient:
    def __init__(self) -> None:
        self.login = Mock(return_value=object())
        self.ensure_authenticated = Mock(return_value=object())
        self.get_activity = Mock(
            return_value={
                "activityId": "123456789",
                "startTimeLocal": "2026-04-19 10:00:00",
            }
        )
        self.get_activity_splits = Mock(return_value=[{"splitNumber": 1}])
        self.get_activity_details = Mock(return_value={"activityDetailMetrics": []})
        self.get_activity_hr_zones = Mock(return_value={"zone1": 10})
        self.get_daily_stats = Mock(return_value={"restingHeartRate": 47})
        self.get_training_status = Mock(
            return_value={"dailyTrainingLoad": 142, "fitnessState": "productive"}
        )
        self.get_stats_and_body_composition = Mock(return_value={"trainingLoad": 142})
        self.get_sleep_data = Mock(return_value={"dailySleepDTO": {}})
        self.get_hrv_data = Mock(return_value={"hrvSummary": {}})
        self.get_body_battery = Mock(return_value=[])


class FakeMarkdownRenderer:
    def __init__(self) -> None:
        self.render_activity = Mock(return_value="---\nactivity_id: 123456789\n---\n")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def normalized_activity() -> NormalizedActivity:
    return NormalizedActivity(
        summary=ActivitySummary(
            activity_id="123456789",
            date=date(2026, 4, 19),
            activity_type="running",
            title="Endurance fondamentale",
        ),
        physiology=PhysiologySnapshot(),
        splits=[],
    )


def override_dependencies(
    garmin_client: FakeGarminClient,
    renderer: FakeMarkdownRenderer,
) -> None:
    async def override_garmin_client() -> FakeGarminClient:
        return garmin_client

    async def override_markdown_renderer() -> FakeMarkdownRenderer:
        return renderer

    app.dependency_overrides[get_garmin_client] = override_garmin_client
    app.dependency_overrides[get_markdown_renderer] = override_markdown_renderer


def clear_overrides() -> None:
    app.dependency_overrides.clear()


def auth_headers() -> dict[str, str]:
    token = token_manager.create_access_token("runner@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_export_markdown_returns_success_json(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    normalized_activity: NormalizedActivity,
) -> None:
    garmin_client = FakeGarminClient()
    renderer = FakeMarkdownRenderer()
    mapper = Mock(return_value=normalized_activity)
    monkeypatch.setattr("app.api.routes_exports.map_activity", mapper)
    override_dependencies(garmin_client, renderer)

    try:
        response = await api_client.post(
            "/api/exports/markdown",
            json={
                "activity_id": "123456789",
                "notes": "#chaleur",
            },
            headers=auth_headers(),
        )
    finally:
        clear_overrides()

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["markdown"].startswith("---")
    assert response.json()["metadata"]["activity_count"] == 1
    garmin_client.login.assert_not_called()
    garmin_client.ensure_authenticated.assert_called_once_with()
    garmin_client.get_activity.assert_called_once_with("123456789")
    garmin_client.get_activity_splits.assert_called_once_with("123456789")
    garmin_client.get_activity_details.assert_called_once_with("123456789")
    garmin_client.get_activity_hr_zones.assert_called_once_with("123456789")
    garmin_client.get_daily_stats.assert_called_once_with(date(2026, 4, 19))
    garmin_client.get_training_status.assert_called_once_with(date(2026, 4, 19))
    garmin_client.get_stats_and_body_composition.assert_called_once_with(date(2026, 4, 19))
    garmin_client.get_sleep_data.assert_called_once_with(date(2026, 4, 19))
    garmin_client.get_hrv_data.assert_called_once_with(date(2026, 4, 19))
    garmin_client.get_body_battery.assert_called_once_with(date(2026, 4, 19))
    mapper.assert_called_once_with(
        {
            "activityId": "123456789",
            "startTimeLocal": "2026-04-19 10:00:00",
        },
        [{"splitNumber": 1}],
        details_payload={"activityDetailMetrics": []},
        hr_zones_payload={"zone1": 10},
        daily_stats_payload={"restingHeartRate": 47},
        training_status_payload={"dailyTrainingLoad": 142, "fitnessState": "productive"},
        stats_and_body_composition_payload={"trainingLoad": 142},
        sleep_payload={"dailySleepDTO": {}},
        hrv_payload={"hrvSummary": {}},
        body_battery_payload=[],
    )
    renderer.render_activity.assert_called_once_with(normalized_activity, notes="#chaleur")


@pytest.mark.anyio
async def test_export_markdown_uses_existing_session_when_request_has_no_credentials(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    normalized_activity: NormalizedActivity,
) -> None:
    garmin_client = FakeGarminClient()
    renderer = FakeMarkdownRenderer()
    mapper = Mock(return_value=normalized_activity)
    monkeypatch.setattr("app.api.routes_exports.map_activity", mapper)
    override_dependencies(garmin_client, renderer)

    try:
        response = await api_client.post(
            "/api/exports/markdown",
            json={
                "activity_id": "123456789",
                "notes": "#session-persistante",
            },
            headers=auth_headers(),
        )
    finally:
        clear_overrides()

    assert response.status_code == 200
    garmin_client.login.assert_not_called()
    garmin_client.ensure_authenticated.assert_called_once_with()
    garmin_client.get_activity.assert_called_once_with("123456789")


@pytest.mark.anyio
async def test_export_markdown_uses_nested_summary_activity_date_for_health_calls(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    normalized_activity: NormalizedActivity,
) -> None:
    garmin_client = FakeGarminClient()
    garmin_client.get_activity.return_value = {
        "activityId": "123456789",
        "summaryDTO": {
            "startTimeLocal": "2026-04-17 18:45:00",
        },
    }
    renderer = FakeMarkdownRenderer()
    mapper = Mock(return_value=normalized_activity)
    monkeypatch.setattr("app.api.routes_exports.map_activity", mapper)
    override_dependencies(garmin_client, renderer)

    try:
        response = await api_client.post(
            "/api/exports/markdown",
            json={
                "activity_id": "123456789",
            },
            headers=auth_headers(),
        )
    finally:
        clear_overrides()

    assert response.status_code == 200
    garmin_client.get_daily_stats.assert_called_once_with(date(2026, 4, 17))
    garmin_client.get_training_status.assert_called_once_with(date(2026, 4, 17))
    garmin_client.get_stats_and_body_composition.assert_called_once_with(date(2026, 4, 17))
    garmin_client.get_sleep_data.assert_called_once_with(date(2026, 4, 17))
    garmin_client.get_hrv_data.assert_called_once_with(date(2026, 4, 17))
    garmin_client.get_body_battery.assert_called_once_with(date(2026, 4, 17))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exception", "expected_status"),
    [
        (GarminAuthenticationError("bad credentials"), 401),
        (GarminActivityNotFoundError("missing activity"), 404),
        (GarminRateLimitError("rate limited"), 429),
        (GarminConnectionError("garmin unavailable"), 502),
    ],
)
async def test_export_markdown_maps_garmin_errors_to_http_statuses(
    api_client: AsyncClient,
    exception: Exception,
    expected_status: int,
) -> None:
    garmin_client = FakeGarminClient()
    garmin_client.ensure_authenticated.side_effect = exception
    renderer = FakeMarkdownRenderer()
    override_dependencies(garmin_client, renderer)

    try:
        response = await api_client.post(
            "/api/exports/markdown",
            json={
                "activity_id": "123456789",
            },
            headers=auth_headers(),
        )
    finally:
        clear_overrides()

    assert response.status_code == expected_status
    assert response.json()["detail"]


@pytest.mark.anyio
async def test_export_batch_returns_zip_archive_for_multiple_activity_ids(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    garmin_client = FakeGarminClient()
    garmin_client.get_activity.side_effect = [
        {
            "activityId": "activity-1",
            "activityName": "Seance 1",
            "startTimeLocal": "2026-04-19 10:00:00",
        },
        {
            "activityId": "activity-2",
            "activityName": "Seance 2",
            "startTimeLocal": "2026-04-20 10:00:00",
        },
    ]
    renderer = FakeMarkdownRenderer()
    renderer.render_activity = Mock(
        side_effect=[
            "---\nactivity_id: activity-1\n---\n",
            "---\nactivity_id: activity-2\n---\n",
        ]
    )
    activity_one = NormalizedActivity(
        summary=ActivitySummary(
            activity_id="activity-1",
            date=date(2026, 4, 19),
            activity_type="running",
            title="Seance 1",
        ),
        physiology=PhysiologySnapshot(),
        splits=[],
    )
    activity_two = NormalizedActivity(
        summary=ActivitySummary(
            activity_id="activity-2",
            date=date(2026, 4, 20),
            activity_type="running",
            title="Seance 2",
        ),
        physiology=PhysiologySnapshot(),
        splits=[],
    )
    mapper = Mock(
        side_effect=[
            activity_one,
            activity_two,
        ]
    )
    monkeypatch.setattr("app.api.routes_exports.map_activity", mapper)
    override_dependencies(garmin_client, renderer)

    try:
        response = await api_client.post(
            "/api/exports/batch",
            json={
                "activity_ids": ["activity-1", "activity-2"],
                "notes": "#bloc-specifique",
            },
            headers=auth_headers(),
        )
    finally:
        clear_overrides()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment;" in response.headers["content-disposition"]
    garmin_client.ensure_authenticated.assert_called_once_with()
    assert garmin_client.get_activity.call_count == 2
    renderer.render_activity.assert_any_call(activity_one, notes="#bloc-specifique")
    renderer.render_activity.assert_any_call(activity_two, notes="#bloc-specifique")

    archive = ZipFile(BytesIO(response.content))
    file_names = sorted(archive.namelist())
    assert file_names == ["2026-04-19-activity-1.md", "2026-04-20-activity-2.md"]
    assert archive.read("2026-04-19-activity-1.md").decode("utf-8").startswith("---")
    assert archive.read("2026-04-20-activity-2.md").decode("utf-8").startswith("---")


@pytest.mark.anyio
async def test_export_batch_can_return_single_markdown_file(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    garmin_client = FakeGarminClient()
    garmin_client.get_activity.side_effect = [
        {
            "activityId": "activity-1",
            "activityName": "Seance 1",
            "startTimeLocal": "2026-04-19 10:00:00",
        },
        {
            "activityId": "activity-2",
            "activityName": "Seance 2",
            "startTimeLocal": "2026-04-20 10:00:00",
        },
    ]
    renderer = FakeMarkdownRenderer()
    renderer.render_activity = Mock(
        side_effect=[
            "# Seance 1\n\nContenu 1\n",
            "# Seance 2\n\nContenu 2\n",
        ]
    )
    mapper = Mock(
        side_effect=[
            NormalizedActivity(
                summary=ActivitySummary(
                    activity_id="activity-1",
                    date=date(2026, 4, 19),
                    activity_type="running",
                    title="Seance 1",
                ),
                physiology=PhysiologySnapshot(),
                splits=[],
            ),
            NormalizedActivity(
                summary=ActivitySummary(
                    activity_id="activity-2",
                    date=date(2026, 4, 20),
                    activity_type="running",
                    title="Seance 2",
                ),
                physiology=PhysiologySnapshot(),
                splits=[],
            ),
        ]
    )
    monkeypatch.setattr("app.api.routes_exports.map_activity", mapper)
    override_dependencies(garmin_client, renderer)

    try:
        response = await api_client.post(
            "/api/exports/batch",
            json={
                "activity_ids": ["activity-1", "activity-2"],
                "notes": "#bloc-specifique",
                "export_format": "markdown",
            },
            headers=auth_headers(),
        )
    finally:
        clear_overrides()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"].endswith('.md"')
    assert ".zip" not in response.headers["content-disposition"]
    content = response.text
    assert "# Seance 1" in content
    assert "\n\n---\n\n" in content
    assert "# Seance 2" in content


@pytest.mark.anyio
async def test_export_markdown_requires_bearer_token(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/exports/markdown",
        json={"activity_id": "123456789"},
    )

    assert response.status_code == 401
