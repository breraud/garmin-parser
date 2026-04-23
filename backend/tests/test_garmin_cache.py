import logging
from hashlib import sha256
from pathlib import Path
from time import sleep
from unittest.mock import Mock, patch

import pytest

from app.garmin.cache import ActivityCache
from app.garmin.client import GarminClient
from app.garmin.exceptions import (
    GarminAuthenticationError,
    GarminConnectionError,
    GarminRateLimitError,
)


def test_activity_cache_returns_value_until_ttl_expires() -> None:
    now = 1000.0
    cache = ActivityCache(ttl_seconds=30, clock=lambda: now)

    cache.set("activity:123", {"activityId": 123})

    assert cache.get("activity:123") == {"activityId": 123}

    now = 1031.0

    assert cache.get("activity:123") is None


@patch("app.garmin.client.Garmin")
def test_login_wraps_garminconnect_and_returns_session(mock_garmin_class: Mock) -> None:
    garmin_api = Mock()
    garmin_api.login.return_value = (None, None)
    mock_garmin_class.return_value = garmin_api
    client = GarminClient(min_request_interval_seconds=0)

    session = client.login("runner@example.com", "secret")

    mock_garmin_class.assert_called_once_with(
        email="runner@example.com",
        password="secret",
        return_on_mfa=True,
    )
    garmin_api.login.assert_called_once()
    tokenstore = garmin_api.login.call_args.kwargs["tokenstore"]
    assert Path(tokenstore).name == sha256(b"runner@example.com").hexdigest()
    assert session.session_id
    assert session.authenticated is True


@patch("app.garmin.client.Garmin")
def test_login_uses_persistent_session_directory(
    mock_garmin_class: Mock,
    tmp_path: Path,
) -> None:
    garmin_api = Mock()
    garmin_api.login.return_value = (None, None)
    mock_garmin_class.return_value = garmin_api
    session_dir = tmp_path / "session_data"
    client = GarminClient(
        min_request_interval_seconds=0,
        request_timeout_seconds=0.5,
        session_data_dir=session_dir,
    )

    client.login("runner@example.com", "secret")

    assert session_dir.is_dir()
    expected_session_dir = session_dir / sha256(b"runner@example.com").hexdigest()
    assert expected_session_dir.is_dir()
    garmin_api.login.assert_called_once_with(tokenstore=str(expected_session_dir))


@patch("app.garmin.client.Garmin")
def test_ensure_authenticated_can_restore_persisted_tokenstore_without_credentials(
    mock_garmin_class: Mock,
    tmp_path: Path,
) -> None:
    garmin_api = Mock()
    garmin_api.login.return_value = (None, None)
    mock_garmin_class.return_value = garmin_api
    session_dir = tmp_path / "session_data"
    hashed_session_dir = session_dir / sha256(b"runner@example.com").hexdigest()
    hashed_session_dir.mkdir(parents=True)
    client = GarminClient(
        email="runner@example.com",
        min_request_interval_seconds=0,
        request_timeout_seconds=0.5,
        session_data_dir=session_dir,
    )

    session = client.ensure_authenticated()

    assert session.authenticated is True
    mock_garmin_class.assert_called_once_with(
        email="runner@example.com",
        password=None,
        return_on_mfa=True,
    )
    garmin_api.login.assert_called_once_with(tokenstore=str(hashed_session_dir))


@patch("app.garmin.client.Garmin")
def test_login_times_out_when_garmin_auth_tarpits(
    mock_garmin_class: Mock,
    tmp_path: Path,
) -> None:
    garmin_api = Mock()

    def slow_login(*_args: object, **_kwargs: object) -> tuple[None, None]:
        sleep(0.2)
        return (None, None)

    garmin_api.login.side_effect = slow_login
    mock_garmin_class.return_value = garmin_api
    client = GarminClient(
        min_request_interval_seconds=0,
        request_timeout_seconds=0.01,
        session_data_dir=tmp_path / "session_data",
    )

    with pytest.raises(GarminConnectionError, match="timed out"):
        client.login("runner@example.com", "secret")


def test_get_activity_times_out_when_garmin_call_tarpits() -> None:
    garmin_api = Mock()

    def slow_activity(_activity_id: str) -> dict[str, int]:
        sleep(0.2)
        return {"activityId": 123456789}

    garmin_api.get_activity.side_effect = slow_activity
    client = GarminClient(
        api=garmin_api,
        cache=ActivityCache(ttl_seconds=60),
        min_request_interval_seconds=0,
        secondary_request_delay_seconds=0,
        request_timeout_seconds=0.01,
    )

    with pytest.raises(GarminConnectionError, match="timed out"):
        client.get_activity("123456789")


def test_get_activity_uses_cache_for_second_call_with_same_activity_id() -> None:
    garmin_api = Mock()
    garmin_api.get_activity.return_value = {"activityId": 123456789}
    client = GarminClient(
        api=garmin_api,
        cache=ActivityCache(ttl_seconds=60),
        min_request_interval_seconds=0,
        secondary_request_delay_seconds=0,
    )

    first_response = client.get_activity("123456789")
    second_response = client.get_activity("123456789")

    assert first_response == {"activityId": 123456789}
    assert second_response == {"activityId": 123456789}
    garmin_api.get_activity.assert_called_once_with("123456789")


def test_get_activity_splits_uses_dedicated_cache_key() -> None:
    garmin_api = Mock()
    garmin_api.get_activity_splits.return_value = [{"splitNumber": 1}]
    garmin_api.get_activity_typed_splits.return_value = {}
    client = GarminClient(
        api=garmin_api,
        cache=ActivityCache(ttl_seconds=60),
        min_request_interval_seconds=0,
        secondary_request_delay_seconds=0,
    )

    assert client.get_activity_splits("123456789") == {"lapDTOs": [{"splitNumber": 1}]}
    assert client.get_activity_splits("123456789") == {"lapDTOs": [{"splitNumber": 1}]}
    garmin_api.get_activity_splits.assert_called_once_with("123456789")
    garmin_api.get_activity_typed_splits.assert_called_once_with("123456789")


def test_get_activity_splits_prefers_laps_over_typed_intervals_when_available() -> None:
    typed_payload = {"activityIntervals": [{"intervalType": "WARMUP"}]}
    garmin_api = Mock()
    garmin_api.get_activity_typed_splits.return_value = typed_payload
    garmin_api.get_activity_splits.return_value = {"lapDTOs": [{"splitNumber": 1}]}
    client = GarminClient(
        api=garmin_api,
        cache=ActivityCache(ttl_seconds=60),
        min_request_interval_seconds=0,
        secondary_request_delay_seconds=0,
    )

    assert client.get_activity_splits("123456789") == {
        "lapDTOs": [{"splitNumber": 1}],
        "activityIntervals": [{"intervalType": "WARMUP"}],
    }
    assert client.get_activity_splits("123456789") == {
        "lapDTOs": [{"splitNumber": 1}],
        "activityIntervals": [{"intervalType": "WARMUP"}],
    }
    garmin_api.get_activity_splits.assert_called_once_with("123456789")
    garmin_api.get_activity_typed_splits.assert_called_once_with("123456789")


def test_get_activity_splits_uses_cache_when_garmin_returns_container_payload() -> None:
    splits_payload = {"splitSummaries": [{"splitNumber": 1}]}
    garmin_api = Mock()
    garmin_api.get_activity_typed_splits.return_value = {}
    garmin_api.get_activity_splits.return_value = splits_payload
    client = GarminClient(
        api=garmin_api,
        cache=ActivityCache(ttl_seconds=60),
        min_request_interval_seconds=0,
        secondary_request_delay_seconds=0,
    )

    assert client.get_activity_splits("123456789") == splits_payload
    assert client.get_activity_splits("123456789") == splits_payload
    garmin_api.get_activity_splits.assert_called_once_with("123456789")


def test_get_activity_details_and_daily_context_use_cache() -> None:
    garmin_api = Mock()
    garmin_api.get_activity_details.return_value = {"activityDetailMetrics": []}
    garmin_api.get_activity_hr_in_timezones.return_value = {"zone1": 120}
    garmin_api.get_user_summary.return_value = {"restingHeartRate": 47}
    garmin_api.get_training_status.return_value = {"dailyTrainingLoad": 142}
    garmin_api.get_sleep_data.return_value = {"dailySleepDTO": {}}
    garmin_api.get_hrv_data.return_value = {"hrvSummary": {}}
    garmin_api.get_body_battery.return_value = [{"bodyBatteryValuesArray": []}]
    client = GarminClient(
        api=garmin_api,
        cache=ActivityCache(ttl_seconds=60),
        min_request_interval_seconds=0,
        secondary_request_delay_seconds=0,
    )

    assert client.get_activity_details("123456789") == {"activityDetailMetrics": []}
    assert client.get_activity_details("123456789") == {"activityDetailMetrics": []}
    assert client.get_activity_hr_zones("123456789") == {"zone1": 120}
    assert client.get_activity_hr_zones("123456789") == {"zone1": 120}
    assert client.get_daily_stats("2026-04-19") == {"restingHeartRate": 47}
    assert client.get_daily_stats("2026-04-19") == {"restingHeartRate": 47}
    assert client.get_training_status("2026-04-19") == {"dailyTrainingLoad": 142}
    assert client.get_training_status("2026-04-19") == {"dailyTrainingLoad": 142}
    assert client.get_sleep_data("2026-04-19") == {"dailySleepDTO": {}}
    assert client.get_sleep_data("2026-04-19") == {"dailySleepDTO": {}}
    assert client.get_hrv_data("2026-04-19") == {"hrvSummary": {}}
    assert client.get_hrv_data("2026-04-19") == {"hrvSummary": {}}
    assert client.get_body_battery("2026-04-19") == [{"bodyBatteryValuesArray": []}]
    assert client.get_body_battery("2026-04-19") == [{"bodyBatteryValuesArray": []}]
    garmin_api.get_activity_details.assert_called_once_with("123456789")
    garmin_api.get_activity_hr_in_timezones.assert_called_once_with("123456789")
    garmin_api.get_user_summary.assert_called_once_with("2026-04-19")
    garmin_api.get_training_status.assert_called_once_with("2026-04-19")
    garmin_api.get_sleep_data.assert_called_once_with("2026-04-19")
    garmin_api.get_hrv_data.assert_called_once_with("2026-04-19")
    garmin_api.get_body_battery.assert_called_once_with("2026-04-19")


def test_secondary_activity_enrichment_calls_fail_safe_and_log_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    garmin_api = Mock()
    garmin_api.get_activity_details.side_effect = Exception("details unavailable")
    garmin_api.get_activity_hr_in_timezones.side_effect = Exception("hr zones unavailable")
    garmin_api.get_user_summary.side_effect = Exception("daily stats unavailable")
    garmin_api.get_training_status.side_effect = Exception("training status unavailable")
    garmin_api.get_sleep_data.side_effect = Exception("sleep unavailable")
    garmin_api.get_hrv_data.side_effect = Exception("hrv unavailable")
    garmin_api.get_body_battery.side_effect = Exception("body battery unavailable")
    client = GarminClient(
        api=garmin_api,
        cache=ActivityCache(ttl_seconds=60),
        min_request_interval_seconds=0,
        secondary_request_delay_seconds=0,
    )

    with caplog.at_level(logging.WARNING, logger="app.garmin.client"):
        assert client.get_activity_details("123456789") == {}
        assert client.get_activity_hr_zones("123456789") == {}
        assert client.get_daily_stats("2026-04-19") == {}
        assert client.get_training_status("2026-04-19") == {}
        assert client.get_sleep_data("2026-04-19") == {}
        assert client.get_hrv_data("2026-04-19") == {}
        assert client.get_body_battery("2026-04-19") == []

    assert "Impossible de récupérer les détails de l'activité Garmin" in caplog.text
    assert "Impossible de récupérer les zones FC Garmin" in caplog.text
    assert "Impossible de récupérer les statistiques journalières Garmin" in caplog.text
    assert "Impossible de récupérer le statut d'entraînement Garmin" in caplog.text
    assert "Impossible de récupérer les données de sommeil Garmin" in caplog.text
    assert "Impossible de récupérer les données HRV Garmin" in caplog.text
    assert "Impossible de récupérer le Body Battery Garmin" in caplog.text


def test_secondary_activity_enrichment_calls_sleep_before_network_request() -> None:
    garmin_api = Mock()
    garmin_api.get_activity_details.return_value = {"activityDetailMetrics": []}
    sleeper = Mock()
    client = GarminClient(
        api=garmin_api,
        cache=ActivityCache(ttl_seconds=60),
        min_request_interval_seconds=0,
        secondary_request_delay_seconds=1,
        sleeper=sleeper,
    )

    assert client.get_activity_details("123456789") == {"activityDetailMetrics": []}

    sleeper.assert_called_once_with(1)
    garmin_api.get_activity_details.assert_called_once_with("123456789")


@patch("app.garmin.client.Garmin")
def test_login_maps_authentication_errors(mock_garmin_class: Mock) -> None:
    garmin_api = Mock()
    garmin_api.login.side_effect = Exception("unauthorized")
    mock_garmin_class.return_value = garmin_api
    client = GarminClient(min_request_interval_seconds=0)

    with pytest.raises(GarminAuthenticationError):
        client.login("runner@example.com", "wrong-password")


@patch("app.garmin.client.Garmin")
def test_login_maps_textual_rate_limit_errors(mock_garmin_class: Mock) -> None:
    garmin_api = Mock()
    garmin_api.login.side_effect = Exception("IP rate limited by Garmin")
    mock_garmin_class.return_value = garmin_api
    client = GarminClient(min_request_interval_seconds=0)

    with pytest.raises(GarminRateLimitError):
        client.login("runner@example.com", "secret")
