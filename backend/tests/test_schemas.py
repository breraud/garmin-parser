from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.auth import AuthCompleteRequest, AuthStartRequest
from app.schemas.exports import MarkdownExportRequest, MarkdownExportResponse
from app.schemas.internal import (
    ActivitySummary,
    HeartRateZone,
    NormalizedActivity,
    PhysiologySnapshot,
    Split,
    TimeSeriesPoint,
)


def test_normalized_activity_accepts_missing_optional_garmin_metrics() -> None:
    summary = ActivitySummary(
        activity_id="123456789",
        date=date(2026, 4, 19),
        activity_type="running",
        title="Endurance fondamentale",
        distance_km=10.24,
        duration_seconds=3133,
        average_pace_min_per_km=5.1,
        average_hr=148,
    )

    activity = NormalizedActivity(
        summary=summary,
        physiology=PhysiologySnapshot(),
        splits=[
            Split(
                index=1,
                distance_km=1.0,
                duration_seconds=318,
                pace_min_per_km=5.3,
                average_hr=137,
            )
        ],
        heart_rate_zones=[HeartRateZone(zone="Z1", duration_seconds=120)],
        time_series=[
            TimeSeriesPoint(
                elapsed_seconds=0,
                distance_km=0.01,
                heart_rate=131,
                pace_min_per_km=5.7,
                elevation_m=120,
                cadence_spm=166,
                power_w=250,
            )
        ],
    )

    assert activity.summary.training_load is None
    assert activity.summary.avg_power is None
    assert activity.summary.avg_stride_length is None
    assert activity.summary.start_stamina is None
    assert activity.summary.fitness_state is None
    assert activity.physiology.hrv_avg_ms is None
    assert activity.physiology.body_battery_start is None
    assert activity.physiology.body_battery_end is None
    assert activity.splits[0].step_type == "Course"
    assert activity.splits[0].max_hr is None
    assert activity.heart_rate_zones[0].zone == "Z1"
    assert activity.time_series[0].elapsed_seconds == 0
    assert activity.time_series[0].power_w == 250


def test_auth_requests_keep_password_secret_and_mfa_code() -> None:
    start_request = AuthStartRequest(email="runner@example.com", password="not-logged")
    complete_request = AuthCompleteRequest(auth_session_id="session-123", mfa_code="123456")

    assert start_request.email == "runner@example.com"
    assert start_request.password.get_secret_value() == "not-logged"
    assert complete_request.auth_session_id == "session-123"
    assert complete_request.mfa_code == "123456"


def test_single_activity_export_request_requires_activity_id() -> None:
    with pytest.raises(ValidationError):
        MarkdownExportRequest(mode="single_activity")

    request = MarkdownExportRequest(
        mode="single_activity",
        activity_id="123456789",
        notes="#chaleur #chaussures",
    )

    assert request.activity_id == "123456789"
    assert request.notes == "#chaleur #chaussures"


def test_single_activity_export_request_accepts_persisted_session_without_credentials() -> None:
    request = MarkdownExportRequest(
        mode="single_activity",
        activity_id="123456789",
    )

    assert request.activity_id == "123456789"
    assert request.mode == "single_activity"


def test_markdown_export_response_contains_markdown_and_metadata() -> None:
    response = MarkdownExportResponse(
        status="success",
        markdown="---\nactivity_id: 123456789\n---\n",
        metadata={"activity_count": 1, "generated_at": "2026-04-19T12:00:00Z"},
    )

    assert response.status == "success"
    assert response.markdown.startswith("---")
    assert response.metadata["activity_count"] == 1
