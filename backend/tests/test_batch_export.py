from collections.abc import AsyncIterator
from datetime import date
from unittest.mock import Mock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes_exports import get_garmin_client, get_markdown_renderer
from app.core.auth import token_manager
from app.main import app
from app.schemas.internal import ActivitySummary, NormalizedActivity, PhysiologySnapshot


class FakeGarminClient:
    def __init__(self) -> None:
        self.login = Mock(return_value=object())
        self.ensure_authenticated = Mock(return_value=object())
        self.list_running_activities = Mock(
            return_value=[
                {"activityId": "activity-1"},
                {"activityId": "activity-2"},
                {"activityId": "activity-3"},
            ]
        )
        self.get_activity = Mock(
            side_effect=[
                {"activityId": "activity-1", "startTimeLocal": "2026-04-19 10:00:00"},
                {"activityId": "activity-2", "startTimeLocal": "2026-04-20 10:00:00"},
            ]
        )
        self.get_activity_splits = Mock(
            side_effect=[
                [{"splitNumber": 1, "activityId": "activity-1"}],
                [{"splitNumber": 1, "activityId": "activity-2"}],
            ]
        )
        self.get_activity_details = Mock(
            side_effect=[
                {"activityDetailMetrics": [{"activityId": "activity-1"}]},
                {"activityDetailMetrics": [{"activityId": "activity-2"}]},
            ]
        )
        self.get_activity_hr_zones = Mock(
            side_effect=[
                {"zone1": 10, "activityId": "activity-1"},
                {"zone1": 20, "activityId": "activity-2"},
            ]
        )
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
        self.render_batch = Mock(return_value="---\nactivity_count: 2\n---\n")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def normalized_activity(activity_id: str) -> NormalizedActivity:
    return NormalizedActivity(
        summary=ActivitySummary(
            activity_id=activity_id,
            date=date(2026, 4, 19),
            activity_type="running",
            title=f"Run {activity_id}",
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
async def test_batch_export_limits_activities_and_renders_markdown(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    garmin_client = FakeGarminClient()
    renderer = FakeMarkdownRenderer()
    mapper = Mock(
        side_effect=[
            normalized_activity("activity-1"),
            normalized_activity("activity-2"),
        ]
    )
    monkeypatch.setattr("app.api.routes_exports.map_activity", mapper)
    override_dependencies(garmin_client, renderer)

    try:
        response = await api_client.post(
            "/api/exports/batch-markdown",
            json={
                "mode": "date_range",
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "max_activities": 2,
                "notes": "#cycle-printemps",
            },
            headers=auth_headers(),
        )
    finally:
        clear_overrides()

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["metadata"]["activity_count"] == 2
    assert response.json()["markdown"].startswith("---")
    garmin_client.login.assert_not_called()
    garmin_client.ensure_authenticated.assert_called_once_with()
    garmin_client.list_running_activities.assert_called_once_with(
        date(2026, 4, 1),
        date(2026, 4, 30),
        2,
    )
    assert garmin_client.get_activity.call_count == 2
    garmin_client.get_activity.assert_any_call("activity-1")
    garmin_client.get_activity.assert_any_call("activity-2")
    garmin_client.get_activity_splits.assert_any_call("activity-1")
    garmin_client.get_activity_splits.assert_any_call("activity-2")
    garmin_client.get_activity_details.assert_any_call("activity-1")
    garmin_client.get_activity_details.assert_any_call("activity-2")
    garmin_client.get_activity_hr_zones.assert_any_call("activity-1")
    garmin_client.get_activity_hr_zones.assert_any_call("activity-2")
    assert garmin_client.get_daily_stats.call_count == 2
    assert garmin_client.get_daily_stats.call_args_list[0].args == (date(2026, 4, 19),)
    assert garmin_client.get_daily_stats.call_args_list[1].args == (date(2026, 4, 20),)
    assert garmin_client.get_training_status.call_count == 2
    assert garmin_client.get_training_status.call_args_list[0].args == (date(2026, 4, 19),)
    assert garmin_client.get_training_status.call_args_list[1].args == (date(2026, 4, 20),)
    assert garmin_client.get_stats_and_body_composition.call_count == 2
    assert garmin_client.get_stats_and_body_composition.call_args_list[0].args == (
        date(2026, 4, 19),
    )
    assert garmin_client.get_stats_and_body_composition.call_args_list[1].args == (
        date(2026, 4, 20),
    )
    assert garmin_client.get_sleep_data.call_count == 2
    assert garmin_client.get_sleep_data.call_args_list[0].args == (date(2026, 4, 19),)
    assert garmin_client.get_sleep_data.call_args_list[1].args == (date(2026, 4, 20),)
    assert garmin_client.get_hrv_data.call_count == 2
    assert garmin_client.get_hrv_data.call_args_list[0].args == (date(2026, 4, 19),)
    assert garmin_client.get_hrv_data.call_args_list[1].args == (date(2026, 4, 20),)
    assert garmin_client.get_body_battery.call_count == 2
    assert garmin_client.get_body_battery.call_args_list[0].args == (date(2026, 4, 19),)
    assert garmin_client.get_body_battery.call_args_list[1].args == (date(2026, 4, 20),)
    assert mapper.call_count == 2
    renderer.render_batch.assert_called_once()
    rendered_activities = renderer.render_batch.call_args.args[0]
    assert [activity.summary.activity_id for activity in rendered_activities] == [
        "activity-1",
        "activity-2",
    ]
    assert renderer.render_batch.call_args.kwargs == {"notes": "#cycle-printemps"}
