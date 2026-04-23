import json
from pathlib import Path

import pytest

from app.processing.mapper import map_activity
from app.processing.metrics import meters_to_kilometers, speed_mps_to_pace_min_per_km

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str) -> object:
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))


def test_metrics_convert_meters_and_speed_to_llm_friendly_values() -> None:
    assert meters_to_kilometers(10240.0) == 10.24
    assert meters_to_kilometers(None) is None
    assert speed_mps_to_pace_min_per_km(3.0) == pytest.approx(5.5555555)
    assert speed_mps_to_pace_min_per_km(0.0) is None
    assert speed_mps_to_pace_min_per_km(None) is None


def test_map_activity_converts_garmin_summary_and_splits() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = load_fixture("garmin_activity_splits.json")

    activity = map_activity(summary_payload, splits_payload)

    assert activity.summary.activity_id == "123456789"
    assert activity.summary.date.isoformat() == "2026-04-19"
    assert activity.summary.activity_type == "running"
    assert activity.summary.title == "Endurance fondamentale"
    assert activity.summary.distance_km == 10.24
    assert activity.summary.duration_seconds == 3133
    assert activity.summary.moving_duration_seconds == 3100
    assert activity.summary.average_pace_min_per_km == pytest.approx(5.0999592)
    assert activity.summary.average_hr == 148
    assert activity.summary.max_hr == 174
    assert activity.summary.training_load == 142.0
    assert activity.summary.fitness_state == "productive"
    assert activity.summary.training_effect_aerobic == 3.2
    assert activity.summary.training_effect_anaerobic == 0.8
    assert activity.summary.elevation_gain_m == 86.0
    assert activity.summary.elevation_loss_m == 74.0
    assert activity.summary.calories == 640
    assert activity.summary.vo2max == 52.0
    assert activity.summary.weather == "clear"
    assert activity.summary.avg_power == 256.0
    assert activity.summary.max_power == 612.0
    assert activity.summary.avg_stride_length == 1.18
    assert activity.summary.avg_vertical_ratio == 7.4
    assert activity.summary.avg_vertical_oscillation == 8.7
    assert activity.summary.avg_ground_contact_time == 241.0
    assert activity.summary.start_stamina == 91.0
    assert activity.summary.end_stamina == 43.0
    assert activity.summary.min_stamina == 39.0

    assert activity.physiology.hrv_avg_ms is None
    assert activity.physiology.body_battery_start is None
    assert len(activity.splits) == 3
    assert activity.splits[0].index == 1
    assert activity.splits[0].step_type == "Échauffement"
    assert activity.splits[0].distance_km == 1.0
    assert activity.splits[0].duration_seconds == 318
    assert activity.splits[0].pace_min_per_km == pytest.approx(5.2994171)
    assert activity.splits[0].average_hr == 137
    assert activity.splits[0].max_hr == 149
    assert activity.splits[0].elevation_gain_m == 8.0
    assert activity.splits[0].elevation_loss_m == 2.0
    assert activity.splits[0].cadence_spm == 168.0
    assert activity.splits[0].stride_length_m == 1.12
    assert activity.splits[1].step_type == "Course"
    assert activity.splits[2].step_type == "Repos"
    assert activity.splits[2].pace_min_per_km == pytest.approx(5.25)
    assert activity.splits[2].average_hr is None


def test_map_activity_numbers_laps_with_enumerate_when_garmin_omits_split_index() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = [
        {"distance": 400.0, "duration": 78.0},
        {"distance": 600.0, "duration": 230.0},
        {"distance": 1000.0, "duration": 318.0},
    ]

    activity = map_activity(summary_payload, splits_payload)

    assert [split.index for split in activity.splits] == [1, 2, 3]
    assert [split.distance_km for split in activity.splits] == [0.4, 0.6, 1.0]
    assert [split.step_type for split in activity.splits] == ["Course", "Course", "Course"]


def test_map_activity_translates_semantic_interval_types_from_garmin_keys() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = [
        {"distance": 1000.0, "duration": 300.0, "splitType": "WARMUP"},
        {"distance": 400.0, "duration": 84.0, "lapType": "INTERVAL_ACTIVE"},
        {"distance": 200.0, "duration": 90.0, "intervalType": "INTERVAL_REST"},
        {"distance": 1000.0, "duration": 420.0, "stepType": "COOLDOWN"},
        {"distance": 100.0, "duration": 60.0, "stepType": "REST"},
        {
            "distance": 200.0,
            "duration": 95.0,
            "stepType": "RUN",
            "splitType": "INTERVAL_REST",
        },
    ]

    activity = map_activity(summary_payload, splits_payload)

    assert [split.step_type for split in activity.splits] == [
        "Échauffement",
        "Course",
        "Repos",
        "Retour au calme",
        "Repos",
        "Repos",
    ]


def test_map_activity_extracts_real_summarydto_advanced_metrics_and_recovery() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Fractionne",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
            "averageHR": 151,
            "maxHR": 183,
            "aerobicTrainingEffect": 3.8,
            "anaerobicTrainingEffect": 2.4,
            "vO2MaxValue": 53.0,
            "recoveryTime": 21.0,
            "power": {
                "avgPower": 279,
                "maxPower": 651,
            },
            "runningDynamics": {
                "avgStrideLength": 1.21,
                "avgVerticalRatio": 7.2,
                "avgVerticalOscillation": 8.1,
                "avgGroundContactTime": 236,
            },
            "staminaDataDTO": {
                "startStamina": 89,
                "endStamina": 42,
                "minStamina": 38,
            },
        },
    }

    activity = map_activity(
        summary_payload,
        daily_stats_payload={"calendarDate": "2026-04-20", "restingHeartRate": 45},
    )

    assert activity.summary.vo2max == 53.0
    assert activity.summary.avg_power == 279.0
    assert activity.summary.max_power == 651.0
    assert activity.summary.avg_stride_length == 1.21
    assert activity.summary.avg_vertical_ratio == 7.2
    assert activity.summary.avg_vertical_oscillation == 8.1
    assert activity.summary.avg_ground_contact_time == 236.0
    assert activity.summary.start_stamina == 89.0
    assert activity.summary.end_stamina == 42.0
    assert activity.summary.min_stamina == 38.0
    assert activity.physiology.recovery_time_hours == 21.0
    assert activity.physiology.resting_hr == 45


def test_map_activity_uses_alternative_training_effect_and_daily_status_keys() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Seuil",
        "startTimeLocal": "2026-04-20 18:30:00",
        "trainingEffect": 3.7,
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
            "anaerobicTrainingEffect": 0.4,
        },
    }

    activity = map_activity(
        summary_payload,
        daily_stats_payload={
            "trainingLoad": 187.0,
            "fitnessQuantity": "maintaining",
        },
    )

    assert activity.summary.training_effect_aerobic == 3.7
    assert activity.summary.training_effect_anaerobic == 0.4
    assert activity.summary.training_load == 187.0
    assert activity.summary.fitness_state == "maintaining"


def test_map_activity_prefers_activity_training_load_from_summarydto() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Seuil",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
            "activityTrainingLoad": 176.0,
        },
    }

    activity = map_activity(
        summary_payload,
        training_status_payload={
            "dailyTrainingLoad": 214.0,
            "acuteTrainingLoad": 198.0,
        },
    )

    assert activity.summary.training_load == 176.0


def test_map_activity_uses_training_status_payload_for_load_and_fitness_state() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Seuil",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
        },
    }

    activity = map_activity(
        summary_payload,
        training_status_payload={
            "dailyTrainingLoad": 214.0,
            "fitnessState": "productive",
        },
    )

    assert activity.summary.training_load == 214.0
    assert activity.summary.fitness_state == "productive"


def test_map_activity_uses_most_recent_training_status_when_top_level_fitness_state_is_missing(
) -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Seuil",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
        },
    }

    activity = map_activity(
        summary_payload,
        training_status_payload={
            "mostRecentTrainingStatus": [
                {"fitnessQuantity": "maintaining"},
            ]
        },
    )

    assert activity.summary.fitness_state == "maintaining"


def test_map_activity_uses_training_status_acute_training_load_when_daily_value_is_missing(
) -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Seuil",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
        },
    }

    activity = map_activity(
        summary_payload,
        training_status_payload={
            "acuteTrainingLoad": 198.0,
            "fitnessState": "productive",
        },
    )

    assert activity.summary.training_load == 198.0


def test_map_activity_uses_training_status_payload_for_vo2max_when_activity_is_missing_it() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Seuil",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
        },
    }

    activity = map_activity(
        summary_payload,
        training_status_payload={
            "dailyTrainingLoad": 214.0,
            "fitnessState": "productive",
            "vo2Max": 53.0,
        },
    )

    assert activity.summary.training_load == 214.0
    assert activity.summary.fitness_state == "productive"
    assert activity.summary.vo2max == 53.0


def test_map_activity_uses_all_training_loads_when_daily_training_load_is_missing() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Seuil",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
        },
    }

    activity = map_activity(
        summary_payload,
        training_status_payload={
            "fitnessState": "productive",
            "allTrainingLoads": [
                {"type": "DAILY", "load": 231.0},
                {"type": "ACUTE", "load": 187.0},
            ],
        },
    )

    assert activity.summary.training_load == 231.0


def test_map_activity_uses_stats_and_body_composition_training_load_when_status_is_empty() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Seuil",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
        },
    }

    activity = map_activity(
        summary_payload,
        training_status_payload={},
        stats_and_body_composition_payload={"trainingLoad": 244.0},
    )

    assert activity.summary.training_load == 244.0


def test_map_activity_derives_running_dynamics_from_activity_detail_metrics() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Footing",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
        },
    }
    details_payload = {
        "metricDescriptors": [
            {"metricsIndex": 0, "key": "directTimestamp"},
            {"metricsIndex": 1, "key": "averageStrideLength"},
            {"metricsIndex": 2, "key": "averageVerticalOscillation"},
            {"metricsIndex": 3, "key": "averageGroundContactTime"},
            {"metricsIndex": 4, "key": "averageVerticalRatio"},
            {"metricsIndex": 5, "key": "directPower"},
        ],
        "activityDetailMetrics": [
            {"metrics": [0, 1.18, 8.2, 242, 7.4, 250]},
            {"metrics": [10, 1.22, 8.6, 238, 7.2, 270]},
            {"metrics": [20, 1.20, None, 240, 7.3, 260]},
        ],
    }

    activity = map_activity(summary_payload, details_payload=details_payload)

    assert activity.summary.avg_stride_length == pytest.approx(1.2)
    assert activity.summary.avg_vertical_oscillation == pytest.approx(8.4)
    assert activity.summary.avg_ground_contact_time == pytest.approx(240.0)
    assert activity.summary.avg_vertical_ratio == pytest.approx(7.3)
    assert activity.summary.avg_power == pytest.approx(260.0)
    assert activity.summary.max_power == pytest.approx(270.0)


def test_map_activity_logs_warning_when_running_dynamics_are_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    summary_payload = {
        "activityId": "missing-dynamics",
        "activityName": "Footing",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
        },
    }

    with caplog.at_level("WARNING", logger="app.processing.mapper"):
        activity = map_activity(summary_payload, details_payload={"activityDetailMetrics": []})

    assert activity.summary.avg_stride_length is None
    assert "Dynamiques de course Garmin introuvables" in caplog.text


def test_map_activity_prefers_lap_dtos_over_activity_intervals_for_tours() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = {
        "lapDTOs": [
            {"distance": 1000.0, "duration": 300.0, "stepType": "RUN"},
            {"distance": 500.0, "duration": 180.0, "intent": "REST"},
        ],
        "activityIntervals": [
            {"intervalType": "WARMUP", "totalDistance": 1000.0, "elapsedDuration": 420.0},
            {"intervalType": "ACTIVE", "totalDistance": 400.0, "elapsedDuration": 82.0},
            {"intervalType": "RECOVERY", "totalDistance": 200.0, "elapsedDuration": 95.0},
            {"intervalType": "COOLDOWN", "totalDistance": 1000.0, "elapsedDuration": 480.0},
        ],
    }

    activity = map_activity(summary_payload, splits_payload)

    assert len(activity.splits) == 2
    assert [split.step_type for split in activity.splits] == ["Course", "Repos"]
    assert [split.distance_km for split in activity.splits] == [1.0, 0.5]
    assert [split.duration_seconds for split in activity.splits] == [300, 180]


def test_map_activity_injects_workout_labels_into_lap_dtos_by_position() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = {
        "lapDTOs": [
            {"distance": 1000.0, "duration": 300.0},
            {"distance": 400.0, "duration": 82.0},
            {"distance": 200.0, "duration": 95.0},
            {"distance": 1000.0, "duration": 480.0},
        ],
        "activityIntervals": [
            {"intent": "WARMUP"},
            {"stepType": "ACTIVE"},
            {"intent": "RECOVERY"},
            {"stepType": "COOLDOWN"},
        ],
    }

    activity = map_activity(summary_payload, splits_payload)

    assert len(activity.splits) == 4
    assert [split.step_type for split in activity.splits] == [
        "Échauffement",
        "Course",
        "Récupération",
        "Retour au calme",
    ]


def test_map_activity_injects_workout_labels_into_lap_dtos_by_matching_start_time() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = {
        "lapDTOs": [
            {
                "startTimeGMT": "2026-04-19 06:30:00",
                "distance": 1000.0,
                "duration": 300.0,
            },
            {
                "startTimeGMT": "2026-04-19 06:35:00",
                "distance": 400.0,
                "duration": 82.0,
            },
            {
                "startTimeGMT": "2026-04-19 06:36:22",
                "distance": 200.0,
                "duration": 95.0,
            },
        ],
        "activityIntervals": [
            {"startTimeGMT": "2026-04-19 06:30:00", "intervalType": "WARMUP"},
            {"startTimeGMT": "2026-04-19 06:35:00", "intervalType": "INTERVAL_ACTIVE"},
            {"startTimeGMT": "2026-04-19 06:36:22", "intervalType": "RECOVERY"},
        ],
    }

    activity = map_activity(summary_payload, splits_payload)

    assert [split.step_type for split in activity.splits] == [
        "Échauffement",
        "Course",
        "Récupération",
    ]


def test_map_activity_injects_workout_labels_into_laps_by_interval_time_range() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = {
        "lapDTOs": [
            {
                "startTimeGMT": "2026-04-19 06:30:00",
                "duration": 300.0,
                "distance": 1000.0,
            },
            {
                "startTimeGMT": "2026-04-19 06:35:00",
                "duration": 300.0,
                "distance": 1000.0,
            },
            {
                "startTimeGMT": "2026-04-19 06:40:00",
                "duration": 180.0,
                "distance": 500.0,
            },
        ],
        "activityIntervals": [
            {
                "startTimeGMT": "2026-04-19 06:30:00",
                "elapsedDuration": 600.0,
                "intervalType": "WARMUP",
            },
            {
                "startTimeGMT": "2026-04-19 06:40:00",
                "elapsedDuration": 180.0,
                "intervalType": "RECOVERY",
            },
        ],
    }

    activity = map_activity(summary_payload, splits_payload)

    assert [split.step_type for split in activity.splits] == [
        "Échauffement",
        "Échauffement",
        "Récupération",
    ]


def test_map_activity_uses_begin_timestamp_for_body_battery_window_selection() -> None:
    summary_payload = {
        "activityId": 123456789,
        "activityName": "Sortie dimanche",
        "startTimeLocal": "2026-04-20 14:30:00",
        "beginTimestamp": 1776688200000,
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {"distance": 5000.0, "duration": 600.0},
    }

    activity = map_activity(
        summary_payload,
        body_battery_payload=[
            {
                "calendarDate": "2026-04-20",
                "bodyBatteryValuesArray": [
                    ["2026-04-20T00:00:00Z", 86],
                    ["2026-04-20T12:29:00Z", 55],
                    ["2026-04-20T12:41:00Z", 45],
                    ["2026-04-20T23:59:00Z", 32],
                ],
            }
        ],
    )

    assert activity.physiology.body_battery_start == 55
    assert activity.physiology.body_battery_end == 45


def test_map_activity_aligns_second_based_activity_epoch_with_millisecond_bb_points() -> None:
    summary_payload = {
        "activityId": 123456789,
        "activityName": "Sortie matin",
        "beginTimestamp": 1776631200,
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {"distance": 5000.0, "duration": 600.0},
    }

    activity = map_activity(
        summary_payload,
        body_battery_payload=[
            {
                "bodyBatteryValuesArray": [
                    [1776624000000, 86],
                    [1776631140000, 55],
                    [1776631860000, 45],
                    [1776667140000, 32],
                ]
            }
        ],
    )

    assert activity.physiology.body_battery_start == 55
    assert activity.physiology.body_battery_end == 45


def test_map_activity_injects_workout_labels_from_summary_payload_when_splits_payload_has_only_laps(
) -> None:
    summary_payload = {
        **load_fixture("garmin_activity_summary.json"),
        "splitSummaries": [
            {"stepType": "WARMUP"},
            {"stepType": "ACTIVE"},
            {"stepType": "REST"},
        ],
    }
    splits_payload = {
        "lapDTOs": [
            {"distance": 1000.0, "duration": 318.0},
            {"distance": 1000.0, "duration": 308.0},
            {"distance": 1000.0, "duration": 315.0},
        ]
    }

    activity = map_activity(summary_payload, splits_payload)

    assert [split.step_type for split in activity.splits] == [
        "Échauffement",
        "Course",
        "Repos",
    ]


def test_map_activity_aligns_lap_split_number_with_split_summaries_using_zero_based_offset(
) -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = {
        "lapDTOs": [
            {"splitNumber": 1, "distance": 1000.0, "duration": 300.0},
            {"splitNumber": 2, "distance": 1000.0, "duration": 300.0},
            {"splitNumber": 3, "distance": 1000.0, "duration": 300.0},
            {"splitNumber": 4, "distance": 1000.0, "duration": 300.0},
        ],
        "splitSummaries": [
            {"stepType": "WARMUP"},
            {"stepType": "WARMUP"},
            {"stepType": "WARMUP"},
            {"stepType": "ACTIVE"},
        ],
    }

    activity = map_activity(summary_payload, splits_payload)

    assert [split.step_type for split in activity.splits] == [
        "Échauffement",
        "Échauffement",
        "Échauffement",
        "Course",
    ]


def test_map_activity_prefers_strict_position_over_split_number_for_semantic_lap_labels() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = {
        "lapDTOs": [
            {"splitNumber": 4, "distance": 1000.0, "duration": 300.0},
            {"splitNumber": 5, "distance": 1000.0, "duration": 300.0},
            {"splitNumber": 6, "distance": 1000.0, "duration": 300.0},
            {"splitNumber": 7, "distance": 1000.0, "duration": 300.0},
        ],
        "splitSummaries": [
            {"stepType": "WARMUP"},
            {"stepType": "WARMUP"},
            {"stepType": "WARMUP"},
            {"stepType": "ACTIVE"},
        ],
    }

    activity = map_activity(summary_payload, splits_payload)

    assert [split.step_type for split in activity.splits] == [
        "Échauffement",
        "Échauffement",
        "Échauffement",
        "Course",
    ]


def test_map_activity_uses_pure_position_alignment_for_all_laps_when_lengths_match() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = {
        "lapDTOs": [
            {"splitNumber": 10, "distance": 1000.0, "duration": 300.0},
            {"splitNumber": 11, "distance": 1000.0, "duration": 300.0},
            {"splitNumber": 12, "distance": 1000.0, "duration": 300.0},
        ],
        "splitSummaries": [
            {"stepType": "WARMUP"},
            {"stepType": "RECOVERY"},
            {"stepType": "ACTIVE"},
        ],
    }

    activity = map_activity(summary_payload, splits_payload)

    assert [split.step_type for split in activity.splits] == [
        "Échauffement",
        "Récupération",
        "Course",
    ]


def test_map_activity_extracts_garmin_hr_zones_from_zone_number_list() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    hr_zones_payload = [
        {"zoneNumber": 1, "secsInZone": 120.0},
        {"zoneNumber": 2, "secsInZone": 900.0},
        {"zoneNumber": 3, "secsInZone": 1500.0},
        {"zoneNumber": 4, "secsInZone": 500.0},
        {"zoneNumber": 5, "secsInZone": 113.0},
    ]

    activity = map_activity(summary_payload, hr_zones_payload=hr_zones_payload)

    assert [(zone.zone, zone.duration_seconds) for zone in activity.heart_rate_zones] == [
        ("Z1", 120),
        ("Z2", 900),
        ("Z3", 1500),
        ("Z4", 500),
        ("Z5", 113),
    ]


def test_map_activity_resamples_garmin_detail_offsets_to_many_10s_points() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    details_payload = {
        "activityDetailMetrics": [
            {
                "startTimeInSeconds": second,
                "sumDistance": second * 3.0,
                "directHeartRate": 130 + (second // 10),
                "directSpeed": 3.0,
                "directElevation": 120.0 + (second / 60),
                "directRunCadence": 166,
                "directPower": 240 + (second // 10),
            }
            for second in range(0, 301, 5)
        ]
    }

    activity = map_activity(summary_payload, details_payload=details_payload)

    assert len(activity.time_series) == 31
    assert [point.elapsed_seconds for point in activity.time_series[:4]] == [0, 10, 20, 30]
    assert activity.time_series[-1].elapsed_seconds == 300
    assert activity.time_series[-1].distance_km == pytest.approx(0.9)
    assert activity.time_series[0].power_w == 240.0
    assert activity.time_series[1].power_w == 241.0


def test_map_activity_resamples_garmin_column_oriented_detail_metrics() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    seconds = list(range(0, 301, 5))
    details_payload = {
        "metricDescriptors": [
            {"metricsIndex": 0, "key": "startTimeInSeconds"},
            {"metricsIndex": 1, "key": "sumDistance"},
            {"metricsIndex": 2, "key": "directHeartRate"},
            {"metricsIndex": 3, "key": "directSpeed"},
            {"metricsIndex": 4, "key": "directElevation"},
            {"metricsIndex": 5, "key": "directRunCadence"},
            {"metricsIndex": 6, "key": "directPower"},
        ],
        "activityDetailMetrics": [
            {"metricsIndex": 0, "metrics": seconds},
            {"metricsIndex": 1, "metrics": [second * 3.0 for second in seconds]},
            {"metricsIndex": 2, "metrics": [130 + (second // 10) for second in seconds]},
            {"metricsIndex": 3, "metrics": [3.0 for _second in seconds]},
            {"metricsIndex": 4, "metrics": [120.0 + (second / 60) for second in seconds]},
            {"metricsIndex": 5, "metrics": [166 for _second in seconds]},
            {"metricsIndex": 6, "metrics": [250 + (second // 10) for second in seconds]},
        ],
    }

    activity = map_activity(summary_payload, details_payload=details_payload)

    assert len(activity.time_series) == 31
    assert [point.elapsed_seconds for point in activity.time_series[:5]] == [0, 10, 20, 30, 40]
    assert activity.time_series[-1].elapsed_seconds == 300
    assert activity.time_series[-1].distance_km == pytest.approx(0.9)
    assert activity.time_series[-1].heart_rate == 160
    assert activity.time_series[-1].power_w == 280.0


def test_map_activity_converts_recovery_time_minutes_to_hours() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Seuil",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageSpeed": 2.827,
            "recoveryTime": 1080,
        },
    }

    activity = map_activity(summary_payload)

    assert activity.physiology.recovery_time_hours == 18.0


def test_map_activity_treats_numeric_direct_timestamp_as_elapsed_seconds() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    seconds = list(range(0, 3601, 5))
    details_payload = {
        "metricDescriptors": [
            {"metricsIndex": 0, "key": "directTimestamp"},
            {"metricsIndex": 1, "key": "sumDistance"},
            {"metricsIndex": 2, "key": "directHeartRate"},
            {"metricsIndex": 3, "key": "directSpeed"},
            {"metricsIndex": 4, "key": "directElevation"},
            {"metricsIndex": 5, "key": "directRunCadence"},
        ],
        "activityDetailMetrics": [
            {"metricsIndex": 0, "metrics": seconds},
            {"metricsIndex": 1, "metrics": [second * 3.0 for second in seconds]},
            {"metricsIndex": 2, "metrics": [130 + (second // 120) for second in seconds]},
            {"metricsIndex": 3, "metrics": [3.0 for _second in seconds]},
            {"metricsIndex": 4, "metrics": [120.0 + (second / 600) for second in seconds]},
            {"metricsIndex": 5, "metrics": [166 for _second in seconds]},
        ],
    }

    activity = map_activity(summary_payload, details_payload=details_payload)

    assert len(activity.time_series) == 361
    assert [point.elapsed_seconds for point in activity.time_series[:4]] == [0, 10, 20, 30]
    assert activity.time_series[-1].elapsed_seconds == 3600
    assert activity.time_series[-1].distance_km == pytest.approx(10.8)


def test_map_activity_enriches_hr_zones_daily_context_and_10s_time_series() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = load_fixture("garmin_activity_splits.json")
    details_payload = load_fixture("garmin_activity_details.json")
    hr_zones_payload = load_fixture("garmin_hr_zones.json")
    daily_stats_payload = load_fixture("garmin_daily_stats.json")
    sleep_payload = load_fixture("garmin_sleep_data.json")
    hrv_payload = load_fixture("garmin_hrv_data.json")
    body_battery_payload = load_fixture("garmin_body_battery.json")

    activity = map_activity(
        summary_payload,
        splits_payload,
        details_payload=details_payload,
        hr_zones_payload=hr_zones_payload,
        daily_stats_payload=daily_stats_payload,
        sleep_payload=sleep_payload,
        hrv_payload=hrv_payload,
        body_battery_payload=body_battery_payload,
    )

    assert [(zone.zone, zone.duration_seconds) for zone in activity.heart_rate_zones] == [
        ("Z1", 120),
        ("Z2", 900),
        ("Z3", 1500),
        ("Z4", 500),
        ("Z5", 113),
    ]
    assert activity.physiology.resting_hr == 47
    assert activity.physiology.hrv_status == "BALANCED"
    assert activity.physiology.hrv_avg_ms == 54.0
    assert activity.physiology.body_battery_start is None
    assert activity.physiology.body_battery_end is None
    assert activity.physiology.stress_avg == 28
    assert activity.physiology.sleep_score == 82
    assert activity.physiology.training_readiness == 74
    assert [point.elapsed_seconds for point in activity.time_series] == [0, 10, 20, 30]
    assert activity.time_series[0].distance_km == pytest.approx(0.01)
    assert activity.time_series[0].heart_rate == 131
    assert activity.time_series[0].pace_min_per_km == pytest.approx(5.7471, abs=0.0001)
    assert activity.time_series[3].heart_rate == 141
    assert activity.time_series[3].cadence_spm == 170.0


def test_map_activity_extracts_body_battery_from_raw_timestamp_value_pairs() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")

    activity = map_activity(
        summary_payload,
        body_battery_payload=[
            [1776729600001, 85],
            [1776729600006, 70],
        ],
    )

    assert activity.physiology.body_battery_start is None
    assert activity.physiology.body_battery_end is None


def test_map_activity_extracts_body_battery_nearest_activity_window() -> None:
    summary_payload = {
        "activityId": 123456789,
        "activityName": "Endurance fondamentale",
        "startTimeGMT": "2026-04-19 06:30:00",
        "endTimeGMT": "2026-04-19 07:22:13",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {"distance": 10240.0, "duration": 3133.0},
    }

    activity = map_activity(
        summary_payload,
        body_battery_payload=[
            {
                "calendarDate": "2026-04-19",
                "bodyBatteryValuesArray": [
                    ["2026-04-19T00:00:00", 95],
                    ["2026-04-19T06:30:30", 82],
                    ["2026-04-19T06:31:00", 80],
                    ["2026-04-19T07:21:30", 68],
                    ["2026-04-19T23:59:00", 44],
                ],
            }
        ],
    )

    assert activity.physiology.body_battery_start == 82
    assert activity.physiology.body_battery_end == 68


def test_map_activity_extracts_nearest_body_battery_when_window_has_no_points(
    caplog: pytest.LogCaptureFixture,
) -> None:
    summary_payload = {
        "activityId": 123456789,
        "activityName": "Sortie dimanche",
        "startTimeGMT": "2026-04-19 14:30:00",
        "endTimeGMT": "2026-04-19 15:15:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {"distance": 9000.0, "duration": 2700.0},
    }

    with caplog.at_level("DEBUG", logger="app.processing.mapper"):
        activity = map_activity(
            summary_payload,
            body_battery_payload=[
                {
                    "calendarDate": "2026-04-19",
                    "bodyBatteryValuesArray": [
                        ["2026-04-19T00:00:00Z", 5],
                        ["2026-04-19T14:25:00Z", 71],
                        ["2026-04-19T15:20:00Z", 62],
                        ["2026-04-19T23:59:00Z", 5],
                    ],
                }
            ],
        )

    assert activity.physiology.body_battery_start == 71
    assert activity.physiology.body_battery_end == 62


def test_map_activity_returns_unavailable_body_battery_when_no_point_is_close_enough(
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_payload = {
        "activityId": 123456789,
        "activityName": "Sortie dimanche",
        "beginTimestamp": 1776688200,
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {"distance": 5000.0, "duration": 600.0},
    }

    activity = map_activity(
        summary_payload,
        body_battery_payload=[
            {
                "calendarDate": "2026-04-20",
                "bodyBatteryValuesArray": [
                    [1776624000000, 86],
                    [1776667140000, 32],
                ],
            }
        ],
    )

    captured = capsys.readouterr()

    assert captured.out == ""
    assert activity.physiology.body_battery_start is None
    assert activity.physiology.body_battery_end is None


def test_map_activity_uses_difference_body_battery_when_wellness_timeseries_has_a_gap() -> None:
    summary_payload = {
        "activityId": 123456789,
        "activityName": "Sortie dimanche",
        "beginTimestamp": 1776688200000,
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 5000.0,
            "duration": 600.0,
            "differenceBodyBattery": -11,
        },
    }

    activity = map_activity(
        summary_payload,
        body_battery_payload=[
            {
                "calendarDate": "2026-04-20",
                "bodyBatteryValuesArray": [
                    [1776687900000, 55],
                    [1776667140000, 32],
                ],
            }
        ],
    )

    assert activity.physiology.body_battery_start is None
    assert activity.physiology.body_battery_end is None
    assert activity.physiology.body_battery_impact == -11


def test_map_activity_normalizes_running_dynamic_units() -> None:
    summary_payload = {
        "activityId": 987654321,
        "activityName": "Footing",
        "startTimeLocal": "2026-04-20 18:30:00",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 8200.0,
            "duration": 2900.0,
            "averageStrideLength": 83,
            "averageVerticalOscillation": 87,
            "averageVerticalRatio": 7.2,
            "averageGroundContactTime": 236,
        },
    }
    details_payload = {
        "metricDescriptors": [
            {"metricsIndex": 0, "key": "directTimestamp"},
            {"metricsIndex": 1, "key": "averageStrideLength"},
            {"metricsIndex": 2, "key": "averageVerticalOscillation"},
        ],
        "activityDetailMetrics": [
            {"metrics": [0, 82, 86]},
            {"metrics": [10, 84, 88]},
        ],
    }

    activity = map_activity(summary_payload, details_payload=details_payload)

    assert activity.summary.avg_stride_length == pytest.approx(0.83)
    assert activity.summary.avg_vertical_oscillation == pytest.approx(8.7)


def test_map_activity_accepts_garmin_split_container_payload() -> None:
    summary_payload = load_fixture("garmin_activity_summary.json")
    splits_payload = {
        "splitSummaries": load_fixture("garmin_activity_splits.json"),
        "metadata": {"source": "garmin-connect"},
    }

    activity = map_activity(summary_payload, splits_payload)

    assert len(activity.splits) == 3
    assert activity.splits[0].index == 1
    assert activity.splits[0].distance_km == 1.0


def test_map_activity_handles_missing_and_null_garmin_fields_without_crashing() -> None:
    activity = map_activity(
        {
            "activityId": "minimal-activity",
            "startTimeLocal": "2026-04-20 10:00:00",
            "summaryDTO": {
                "distance": None,
                "duration": None,
                "averageSpeed": None,
                "averageHR": None
            },
        },
        [
            {
                "splitNumber": 1,
                "distance": 1000.0,
                "duration": None,
                "averageSpeed": None,
            }
        ],
    )

    assert activity.summary.activity_id == "minimal-activity"
    assert activity.summary.activity_type == "unknown"
    assert activity.summary.distance_km is None
    assert activity.summary.duration_seconds is None
    assert activity.summary.average_pace_min_per_km is None
    assert activity.summary.training_load is None
    assert activity.summary.max_hr is None
    assert activity.summary.weather is None
    assert activity.splits[0].duration_seconds is None
    assert activity.splits[0].pace_min_per_km is None
