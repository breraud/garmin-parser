import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import pandas as pd  # type: ignore[import-untyped]

from app.processing.metrics import (
    duration_distance_to_pace_min_per_km,
    meters_to_kilometers,
    seconds_to_int,
    speed_mps_to_pace_min_per_km,
)
from app.schemas.internal import (
    ActivitySummary,
    HeartRateZone,
    NormalizedActivity,
    PhysiologySnapshot,
    Split,
    TimeSeriesPoint,
)

GarminPayload = Mapping[str, Any]
logger = logging.getLogger(__name__)
BODY_BATTERY_MAX_DELTA_MS = 15 * 60 * 1000
SPLIT_CONTAINER_KEYS = (
    "lapDTOs",
    "activityIntervals",
    "activityIntervalDTOs",
    "intervals",
    "intervalDTOs",
    "workoutStepDTOs",
    "splitSummaries",
    "splits",
    "activitySplits",
    "splitDTOs",
)
SPLIT_FIELD_KEYS = frozenset(
    {
        "splitNumber",
        "no",
        "index",
        "distance",
        "duration",
        "averageSpeed",
        "averageHR",
        "splitType",
        "intervalType",
        "lapType",
        "stepType",
        "intent",
    }
)


def map_activity(
    summary_payload: GarminPayload,
    splits_payload: object | None = None,
    *,
    details_payload: object | None = None,
    hr_zones_payload: object | None = None,
    daily_stats_payload: object | None = None,
    training_status_payload: object | None = None,
    stats_and_body_composition_payload: object | None = None,
    sleep_payload: object | None = None,
    hrv_payload: object | None = None,
    body_battery_payload: object | None = None,
) -> NormalizedActivity:
    summary_dto = as_mapping(summary_payload.get("summaryDTO"))
    details_dynamics = extract_running_dynamics_from_details(details_payload)
    power_dto = as_mapping(
        first_non_null(
            summary_dto.get("power"),
            summary_dto.get("powerDTO"),
            summary_dto.get("runningPowerDTO"),
            summary_payload.get("power"),
            summary_payload.get("powerDTO"),
        )
    )
    running_dynamics_dto = as_mapping(
        first_non_null(
            summary_dto.get("runningDynamics"),
            summary_dto.get("runningDynamicsDTO"),
            summary_dto.get("runDynamics"),
            summary_payload.get("runningDynamics"),
            summary_payload.get("runningDynamicsDTO"),
        )
    )
    stamina_dto = as_mapping(
        first_non_null(
            summary_payload.get("staminaDTO"),
            summary_payload.get("staminaDataDTO"),
            summary_payload.get("stamina"),
            summary_dto.get("staminaDataDTO"),
            summary_dto.get("staminaDTO"),
            summary_dto.get("stamina"),
        )
    )
    daily_stats = as_mapping(daily_stats_payload)
    training_status = as_mapping(training_status_payload)
    most_recent_training_status = first_mapping_from_sequence(
        training_status.get("mostRecentTrainingStatus")
    )
    stats_and_body_composition = as_mapping(stats_and_body_composition_payload)
    split_payloads = normalize_split_payloads_with_labels(
        merge_split_payload_sources(splits_payload, summary_payload)
    )
    splits = [
        map_split(split_payload, fallback_index=index)
        for index, split_payload in enumerate(split_payloads, start=1)
    ]

    summary = ActivitySummary(
        activity_id=str(summary_payload.get("activityId") or ""),
        date=parse_activity_date(summary_payload),
        activity_type=extract_activity_type(summary_payload),
        title=as_optional_str(summary_payload.get("activityName")),
        distance_km=meters_to_kilometers(as_float(summary_dto.get("distance"))),
        duration_seconds=seconds_to_int(as_float(summary_dto.get("duration"))),
        moving_duration_seconds=seconds_to_int(as_float(summary_dto.get("movingDuration"))),
        average_pace_min_per_km=extract_pace(summary_dto),
        average_hr=as_int(summary_dto.get("averageHR")),
        max_hr=as_int(summary_dto.get("maxHR")),
        training_load=as_float(
            first_non_null(
                summary_dto.get("activityTrainingLoad"),
                summary_payload.get("activityTrainingLoad"),
                summary_dto.get("trainingLoad"),
                summary_payload.get("trainingLoad"),
                daily_stats.get("trainingLoad"),
                daily_stats.get("load"),
                daily_stats.get("acuteTrainingLoad"),
                training_status.get("dailyTrainingLoad"),
                training_status.get("acuteTrainingLoad"),
                training_status.get("trainingLoad"),
                training_status.get("load"),
                extract_training_load_from_status(training_status),
                stats_and_body_composition.get("trainingLoad"),
                stats_and_body_composition.get("load"),
            )
        ),
        fitness_state=as_optional_str(
            first_non_null(
                summary_payload.get("fitnessState"),
                summary_dto.get("fitnessState"),
                training_status.get("fitnessState"),
                training_status.get("fitnessQuantity"),
                training_status.get("trainingStatus"),
                most_recent_training_status.get("fitnessState"),
                most_recent_training_status.get("fitnessQuantity"),
                most_recent_training_status.get("trainingStatus"),
                daily_stats.get("fitnessState"),
                daily_stats.get("fitnessQuantity"),
                daily_stats.get("trainingStatus"),
            )
        ),
        training_effect_aerobic=as_float(
            first_non_null(
                summary_dto.get("aerobicTrainingEffect"),
                summary_dto.get("trainingEffect"),
                summary_payload.get("aerobicTrainingEffect"),
                summary_payload.get("trainingEffect"),
            )
        ),
        training_effect_anaerobic=as_float(summary_dto.get("anaerobicTrainingEffect")),
        elevation_gain_m=as_float(summary_dto.get("elevationGain")),
        elevation_loss_m=as_float(
            first_non_null(
                summary_dto.get("totalDescent"),
                summary_dto.get("elevationLoss"),
                summary_dto.get("totalElevationLoss"),
                summary_dto.get("descent"),
                summary_payload.get("totalDescent"),
                summary_payload.get("elevationLoss"),
            )
        ),
        calories=as_int(summary_dto.get("calories")),
        vo2max=as_float(
            first_non_null(
                summary_payload.get("vO2MaxValue"),
                summary_dto.get("vO2MaxValue"),
                summary_dto.get("vo2MaxValue"),
                training_status.get("vO2MaxValue"),
                training_status.get("vo2MaxValue"),
                training_status.get("vo2Max"),
            )
        ),
        perceived_effort=as_optional_str(summary_payload.get("perceivedEffort")),
        weather=extract_weather(summary_payload),
        avg_power=as_float(
            first_non_null(
                summary_dto.get("avgPower"),
                summary_dto.get("averagePower"),
                power_dto.get("avgPower"),
                power_dto.get("averagePower"),
                summary_payload.get("avgPower"),
                summary_payload.get("averagePower"),
                details_dynamics.get("avg_power"),
            )
        ),
        max_power=as_float(
            first_non_null(
                summary_dto.get("maxPower"),
                summary_dto.get("maximumPower"),
                power_dto.get("maxPower"),
                power_dto.get("maximumPower"),
                summary_payload.get("maxPower"),
                summary_payload.get("maximumPower"),
                details_dynamics.get("max_power"),
            )
        ),
        avg_stride_length=normalize_stride_length(
            first_non_null(
                summary_dto.get("avgStrideLength"),
                summary_dto.get("averageStrideLength"),
                running_dynamics_dto.get("avgStrideLength"),
                running_dynamics_dto.get("averageStrideLength"),
                summary_payload.get("avgStrideLength"),
                summary_payload.get("averageStrideLength"),
                details_dynamics.get("avg_stride_length"),
            )
        ),
        avg_vertical_ratio=as_float(
            first_non_null(
                summary_dto.get("avgVerticalRatio"),
                summary_dto.get("averageVerticalRatio"),
                running_dynamics_dto.get("avgVerticalRatio"),
                running_dynamics_dto.get("averageVerticalRatio"),
                summary_payload.get("avgVerticalRatio"),
                summary_payload.get("averageVerticalRatio"),
                details_dynamics.get("avg_vertical_ratio"),
            )
        ),
        avg_vertical_oscillation=normalize_vertical_oscillation(
            first_non_null(
                summary_dto.get("avgVerticalOscillation"),
                summary_dto.get("averageVerticalOscillation"),
                running_dynamics_dto.get("avgVerticalOscillation"),
                running_dynamics_dto.get("averageVerticalOscillation"),
                summary_payload.get("avgVerticalOscillation"),
                summary_payload.get("averageVerticalOscillation"),
                details_dynamics.get("avg_vertical_oscillation"),
            )
        ),
        avg_ground_contact_time=as_float(
            first_non_null(
                summary_dto.get("avgGroundContactTime"),
                summary_dto.get("averageGroundContactTime"),
                running_dynamics_dto.get("avgGroundContactTime"),
                running_dynamics_dto.get("averageGroundContactTime"),
                summary_payload.get("avgGroundContactTime"),
                summary_payload.get("averageGroundContactTime"),
                details_dynamics.get("avg_ground_contact_time"),
            )
        ),
        start_stamina=as_float(
            first_non_null(
                summary_dto.get("startStamina"),
                summary_dto.get("beginStamina"),
                summary_dto.get("staminaStart"),
                stamina_dto.get("startStamina"),
                stamina_dto.get("beginStamina"),
                stamina_dto.get("staminaStart"),
            )
        ),
        end_stamina=as_float(
            first_non_null(
                summary_dto.get("endStamina"),
                summary_dto.get("staminaEnd"),
                stamina_dto.get("endStamina"),
                stamina_dto.get("staminaEnd"),
            )
        ),
        min_stamina=as_float(
            first_non_null(
                summary_dto.get("minStamina"),
                summary_dto.get("minimumStamina"),
                stamina_dto.get("minStamina"),
                stamina_dto.get("minimumStamina"),
            )
        ),
    )
    log_missing_running_dynamics(summary)

    return NormalizedActivity(
        summary=summary,
        physiology=extract_physiology(
            summary_payload,
            daily_stats_payload=daily_stats_payload,
            sleep_payload=sleep_payload,
            hrv_payload=hrv_payload,
            body_battery_payload=body_battery_payload,
        ),
        splits=splits,
        heart_rate_zones=map_heart_rate_zones(hr_zones_payload),
        time_series=map_time_series(details_payload),
        source_payload=dict(summary_payload),
    )


def map_split(split_payload: GarminPayload, fallback_index: int = 1) -> Split:
    distance_meters = as_float(
        first_non_null(
            split_payload.get("distance"),
            split_payload.get("totalDistance"),
            split_payload.get("totalDistanceMeters"),
            split_payload.get("sumDistance"),
        )
    )
    duration_seconds = as_float(
        first_non_null(
            split_payload.get("duration"),
            split_payload.get("elapsedDuration"),
            split_payload.get("movingDuration"),
            split_payload.get("timerDuration"),
            split_payload.get("totalDuration"),
        )
    )
    pace = speed_mps_to_pace_min_per_km(
        as_float(
            first_non_null(
                split_payload.get("averageSpeed"),
                split_payload.get("avgSpeed"),
            )
        )
    )
    if pace is None:
        pace = duration_distance_to_pace_min_per_km(duration_seconds, distance_meters)

    return Split(
        index=as_int(
            first_non_null(
                split_payload.get("splitNumber"),
                split_payload.get("no"),
                split_payload.get("index"),
                fallback_index,
            )
        )
        or fallback_index,
        step_type=translate_split_type(split_payload),
        distance_km=meters_to_kilometers(distance_meters) or 0.0,
        duration_seconds=seconds_to_int(duration_seconds),
        pace_min_per_km=pace,
        average_hr=as_int(
            first_non_null(
                split_payload.get("averageHR"),
                split_payload.get("averageHeartRate"),
                split_payload.get("avgHeartRate"),
            )
        ),
        max_hr=as_int(
            first_non_null(
                split_payload.get("maxHR"),
                split_payload.get("maxHeartRate"),
            )
        ),
        elevation_gain_m=as_float(split_payload.get("elevationGain")),
        elevation_loss_m=as_float(split_payload.get("elevationLoss")),
        cadence_spm=as_float(
            first_non_null(
                split_payload.get("averageRunCadence"),
                split_payload.get("averageCadence"),
                split_payload.get("avgRunCadence"),
                split_payload.get("avgCadence"),
            )
        ),
        stride_length_m=normalize_stride_length(split_payload.get("strideLength")),
    )


def translate_split_type(split_payload: GarminPayload) -> str:
    raw_code = extract_split_type_code(split_payload)
    if raw_code is None:
        return "Course"

    code = raw_code.upper().replace("-", "_").replace(" ", "_")
    if "WARM" in code:
        return "Échauffement"

    if "COOLDOWN" in code or "COOL_DOWN" in code or "COOL" in code:
        return "Retour au calme"

    if code == "REST":
        return "Repos"

    if "RECOVER" in code or "RECOVERY" in code or "RECUP" in code:
        return "Récupération"

    if "REST" in code:
        return "Repos"

    if "ACTIVE" in code or "RUN" in code or "WORK" in code:
        return "Course"

    return "Course"


def extract_split_type_code(split_payload: GarminPayload) -> str | None:
    logger.debug("Garmin split keys available: %s", sorted(split_payload.keys()))
    for key in (
        "splitType",
        "intervalType",
        "lapType",
        "splitTypeDTO",
        "intervalTypeDTO",
        "lapTypeDTO",
        "stepType",
        "intent",
        "workoutStepType",
    ):
        value = split_payload.get(key)
        value_mapping = as_mapping(value)
        if value_mapping:
            code = as_optional_str(
                first_non_null(
                    value_mapping.get("typeKey"),
                    value_mapping.get("key"),
                    value_mapping.get("value"),
                    value_mapping.get("name"),
                )
            )
            if code is not None:
                return code

        code = as_optional_str(value)
        if code is not None:
            return code

    return None


def normalize_split_payloads(splits_payload: object | None) -> list[GarminPayload]:
    if splits_payload is None:
        return []

    if isinstance(splits_payload, Mapping):
        for container_key in SPLIT_CONTAINER_KEYS:
            nested_payload = splits_payload.get(container_key)
            nested_splits = normalize_split_payloads(nested_payload)
            if nested_splits:
                return nested_splits

        if looks_like_split_payload(splits_payload):
            return [splits_payload]

        return []

    if isinstance(splits_payload, Sequence) and not isinstance(
        splits_payload,
        str | bytes | bytearray,
    ):
        return [
            split_payload
            for split_payload in splits_payload
            if isinstance(split_payload, Mapping)
        ]

    return []


def normalize_split_payloads_with_labels(splits_payload: object | None) -> list[GarminPayload]:
    if not isinstance(splits_payload, Mapping):
        return normalize_split_payloads(splits_payload)

    lap_payloads = normalize_split_payloads(splits_payload.get("lapDTOs"))
    if not lap_payloads:
        return normalize_split_payloads(splits_payload)

    label_payloads = normalize_workout_label_payloads(splits_payload)
    if not label_payloads:
        return lap_payloads

    enriched_laps: list[GarminPayload] = []
    for index, lap_payload in enumerate(lap_payloads):
        if extract_split_type_code(lap_payload) is not None:
            enriched_laps.append(lap_payload)
            continue

        label_payload: GarminPayload | None = None
        if len(label_payloads) == len(lap_payloads) and index < len(label_payloads):
            label_payload = label_payloads[index]
        else:
            fallback_index = extract_split_label_index(lap_payload, index)
            label_payload = find_matching_workout_label_payload(
                lap_payload,
                label_payloads,
                fallback_index=fallback_index,
            )
        label_code = extract_split_type_code(label_payload) if label_payload else None
        if label_code is None:
            enriched_laps.append(lap_payload)
            continue

        enriched_lap = dict(lap_payload)
        enriched_lap["stepType"] = label_code
        enriched_laps.append(enriched_lap)

    return enriched_laps


def extract_split_label_index(split_payload: GarminPayload, default_index: int) -> int:
    explicit_index = as_int(
        first_non_null(
            split_payload.get("splitNumber"),
            split_payload.get("no"),
            split_payload.get("index"),
        )
    )
    if explicit_index is None:
        return default_index

    return max(0, explicit_index - 1)


def merge_split_payload_sources(
    splits_payload: object | None,
    summary_payload: GarminPayload,
) -> object | None:
    splits_mapping = as_mapping(splits_payload)
    summary_mapping = as_mapping(summary_payload)
    if not splits_mapping:
        return splits_payload

    merged = dict(splits_mapping)
    for container_key in (
        "activityIntervals",
        "activityIntervalDTOs",
        "intervals",
        "intervalDTOs",
        "workoutStepDTOs",
        "splitSummaries",
    ):
        existing = merged.get(container_key)
        if existing not in (None, [], {}):
            continue

        fallback = summary_mapping.get(container_key)
        if fallback not in (None, [], {}):
            merged[container_key] = fallback

    return merged


def normalize_workout_label_payloads(splits_payload: GarminPayload) -> list[GarminPayload]:
    for container_key in (
        "activityIntervals",
        "activityIntervalDTOs",
        "intervals",
        "intervalDTOs",
        "workoutStepDTOs",
        "splitSummaries",
    ):
        nested_payload = splits_payload.get(container_key)
        label_payloads = normalize_split_payloads(nested_payload)
        if any(
            extract_split_type_code(label_payload) is not None
            for label_payload in label_payloads
        ):
            return label_payloads

    return []


def find_matching_workout_label_payload(
    lap_payload: GarminPayload,
    label_payloads: Sequence[GarminPayload],
    *,
    fallback_index: int,
) -> GarminPayload | None:
    lap_start = extract_split_start_datetime(lap_payload)
    lap_end = extract_split_end_datetime(lap_payload)
    if lap_start is not None:
        ranged_matches = [
            label_payload
            for label_payload in label_payloads
            if split_payload_contains_range(label_payload, lap_start, lap_end)
        ]
        if ranged_matches:
            return ranged_matches[0]

        timed_matches = [
            (
                abs((label_start - lap_start).total_seconds()),
                label_payload,
            )
            for label_payload in label_payloads
            if (label_start := extract_split_start_datetime(label_payload)) is not None
        ]
        if timed_matches:
            delta_seconds, label_payload = min(timed_matches, key=lambda match: match[0])
            if delta_seconds <= 5:
                return label_payload

    lap_offset_seconds = extract_split_start_offset_seconds(lap_payload)
    lap_end_offset_seconds = extract_split_end_offset_seconds(lap_payload)
    if lap_offset_seconds is not None:
        offset_ranged_matches = [
            label_payload
            for label_payload in label_payloads
            if split_payload_contains_offset_range(
                label_payload,
                lap_offset_seconds,
                lap_end_offset_seconds,
            )
        ]
        if offset_ranged_matches:
            return offset_ranged_matches[0]

        offset_matches = [
            (
                abs(label_offset_seconds - lap_offset_seconds),
                label_payload,
            )
            for label_payload in label_payloads
            if (
                label_offset_seconds := extract_split_start_offset_seconds(label_payload)
            )
            is not None
        ]
        if offset_matches:
            delta_seconds, label_payload = min(offset_matches, key=lambda match: match[0])
            if delta_seconds <= 5:
                return label_payload

    if fallback_index < len(label_payloads):
        return label_payloads[fallback_index]

    return None


def extract_split_start_datetime(split_payload: GarminPayload) -> datetime | None:
    return parse_garmin_datetime(
        first_non_null(
            split_payload.get("startTimeGMT"),
            split_payload.get("startTimeGmt"),
            split_payload.get("startTimeLocal"),
            split_payload.get("beginTimestamp"),
            split_payload.get("startTime"),
            split_payload.get("beginTime"),
        )
    )


def extract_split_start_offset_seconds(split_payload: GarminPayload) -> float | None:
    seconds = as_float(
        first_non_null(
            split_payload.get("startTimeInSeconds"),
            split_payload.get("startTimeSec"),
            split_payload.get("offsetInSeconds"),
            split_payload.get("timeOffsetSeconds"),
            split_payload.get("beginTimeInSeconds"),
            split_payload.get("elapsedStartSeconds"),
        )
    )
    if seconds is not None:
        return seconds

    milliseconds = as_float(
        first_non_null(
            split_payload.get("startTimeInMilliseconds"),
            split_payload.get("startTimeMs"),
            split_payload.get("offsetInMilliseconds"),
            split_payload.get("timeOffsetMs"),
        )
    )
    if milliseconds is None:
        return None

    return milliseconds / 1000


def extract_split_end_datetime(split_payload: GarminPayload) -> datetime | None:
    start = extract_split_start_datetime(split_payload)
    duration_seconds = extract_split_duration_seconds(split_payload)
    if start is None or duration_seconds is None:
        return None

    return start + timedelta(seconds=duration_seconds)


def extract_split_end_offset_seconds(split_payload: GarminPayload) -> float | None:
    start_offset = extract_split_start_offset_seconds(split_payload)
    duration_seconds = extract_split_duration_seconds(split_payload)
    if start_offset is None or duration_seconds is None:
        return None

    return start_offset + duration_seconds


def extract_split_duration_seconds(split_payload: GarminPayload) -> float | None:
    return as_float(
        first_non_null(
            split_payload.get("duration"),
            split_payload.get("elapsedDuration"),
            split_payload.get("movingDuration"),
            split_payload.get("timerDuration"),
            split_payload.get("totalDuration"),
        )
    )


def split_payload_contains_range(
    label_payload: GarminPayload,
    lap_start: datetime,
    lap_end: datetime | None,
) -> bool:
    label_start = extract_split_start_datetime(label_payload)
    label_end = extract_split_end_datetime(label_payload)
    if label_start is None or label_end is None:
        return False

    effective_lap_end = lap_end or lap_start
    return label_start <= lap_start and effective_lap_end <= label_end


def split_payload_contains_offset_range(
    label_payload: GarminPayload,
    lap_start_offset_seconds: float,
    lap_end_offset_seconds: float | None,
) -> bool:
    label_start_offset = extract_split_start_offset_seconds(label_payload)
    label_end_offset = extract_split_end_offset_seconds(label_payload)
    if label_start_offset is None or label_end_offset is None:
        return False

    effective_lap_end = lap_end_offset_seconds or lap_start_offset_seconds
    return (
        label_start_offset <= lap_start_offset_seconds
        and effective_lap_end <= label_end_offset
    )


def looks_like_split_payload(split_payload: GarminPayload) -> bool:
    return any(field_key in split_payload for field_key in SPLIT_FIELD_KEYS)


def extract_running_dynamics_from_details(
    details_payload: object | None,
) -> dict[str, float]:
    rows = normalize_detail_rows(details_payload)
    if not rows:
        return {}

    result: dict[str, float] = {}
    avg_stride_length = average_row_metric(rows, "stride_length")
    avg_vertical_oscillation = average_row_metric(rows, "vertical_oscillation")
    avg_ground_contact_time = average_row_metric(rows, "ground_contact_time")
    avg_vertical_ratio = average_row_metric(rows, "vertical_ratio")
    avg_power = average_row_metric(rows, "power")
    max_power = max_row_metric(rows, "power")

    if avg_stride_length is not None:
        result["avg_stride_length"] = (
            normalize_stride_length(avg_stride_length) or avg_stride_length
        )
    if avg_vertical_oscillation is not None:
        result["avg_vertical_oscillation"] = (
            normalize_vertical_oscillation(avg_vertical_oscillation) or avg_vertical_oscillation
        )
    if avg_ground_contact_time is not None:
        result["avg_ground_contact_time"] = avg_ground_contact_time
    if avg_vertical_ratio is not None:
        result["avg_vertical_ratio"] = avg_vertical_ratio
    if avg_power is not None:
        result["avg_power"] = avg_power
    if max_power is not None:
        result["max_power"] = max_power

    return result


def average_row_metric(rows: Sequence[Mapping[str, object]], key: str) -> float | None:
    values = [number for row in rows if (number := clean_float(row.get(key))) is not None]
    if not values:
        return None

    return sum(values) / len(values)


def max_row_metric(rows: Sequence[Mapping[str, object]], key: str) -> float | None:
    values = [number for row in rows if (number := clean_float(row.get(key))) is not None]
    if not values:
        return None

    return max(values)


def normalize_stride_length(value: object) -> float | None:
    stride = as_float(value)
    if stride is None:
        return None

    if stride > 300:
        return stride / 1000

    if stride > 10:
        return stride / 100

    return stride


def normalize_vertical_oscillation(value: object) -> float | None:
    oscillation = as_float(value)
    if oscillation is None:
        return None

    if oscillation > 30:
        return oscillation / 10

    return oscillation


def normalize_recovery_time_hours(value: object) -> float | None:
    recovery = as_float(value)
    if recovery is None:
        return None

    if recovery > 72:
        return recovery / 60

    return recovery


def log_missing_running_dynamics(summary: ActivitySummary) -> None:
    if any(
        value is not None
        for value in (
            summary.avg_stride_length,
            summary.avg_vertical_ratio,
            summary.avg_vertical_oscillation,
            summary.avg_ground_contact_time,
        )
    ):
        return

    logger.warning(
        "Dynamiques de course Garmin introuvables pour l'activité %s.",
        summary.activity_id,
    )


def map_heart_rate_zones(hr_zones_payload: object | None) -> list[HeartRateZone]:
    zone_payloads = normalize_hr_zone_payloads(hr_zones_payload)
    if zone_payloads:
        zones: list[HeartRateZone] = []
        for zone_payload in zone_payloads:
            zone_mapping = as_mapping(zone_payload)
            zone_number = extract_zone_number(zone_mapping)
            duration_seconds = extract_zone_duration_from_mapping(zone_mapping)
            if zone_number is not None and duration_seconds is not None:
                zones.append(
                    HeartRateZone(
                        zone=f"Z{zone_number}",
                        duration_seconds=duration_seconds,
                    )
                )

        return sorted(zones, key=lambda zone: zone.zone)

    payload = as_mapping(hr_zones_payload)
    if not payload:
        return []

    zones = []
    for zone_number in range(1, 6):
        duration_seconds = extract_zone_duration(payload, zone_number)
        if duration_seconds is not None:
            zones.append(
                HeartRateZone(
                    zone=f"Z{zone_number}",
                    duration_seconds=duration_seconds,
                )
            )

    return zones


def normalize_hr_zone_payloads(hr_zones_payload: object | None) -> list[object]:
    if isinstance(hr_zones_payload, Sequence) and not isinstance(
        hr_zones_payload,
        str | bytes | bytearray,
    ):
        return list(hr_zones_payload)

    payload = as_mapping(hr_zones_payload)
    for key in (
        "zones",
        "heartRateZones",
        "timeInZones",
        "hrTimeInZones",
        "heartRateTimeInZones",
        "activityHrTimeInZones",
    ):
        nested_payload = payload.get(key)
        if isinstance(nested_payload, Sequence) and not isinstance(
            nested_payload,
            str | bytes | bytearray,
        ):
            return list(nested_payload)

    return []


def extract_zone_number(zone_mapping: GarminPayload) -> int | None:
    zone_number = as_int(
        first_non_null(
            zone_mapping.get("zoneNumber"),
            zone_mapping.get("zone"),
            zone_mapping.get("index"),
        )
    )
    if zone_number is None:
        return None

    if 1 <= zone_number <= 5:
        return zone_number

    if zone_number == 0:
        return 1

    return None


def extract_zone_duration_from_mapping(zone_mapping: GarminPayload) -> int | None:
    return seconds_to_int(
        as_float(
            first_non_null(
                zone_mapping.get("secsInZone"),
                zone_mapping.get("secondsInZone"),
                zone_mapping.get("duration"),
                zone_mapping.get("durationSeconds"),
                zone_mapping.get("timeInSeconds"),
                zone_mapping.get("timeInZone"),
            )
        )
    )


def extract_zone_duration(payload: GarminPayload, zone_number: int) -> int | None:
    direct_keys = (
        f"zone{zone_number}",
        f"zone{zone_number}Time",
        f"zone{zone_number}TimeInSeconds",
        f"hrZone{zone_number}",
    )
    for key in direct_keys:
        value = seconds_to_int(as_float(payload.get(key)))
        if value is not None:
            return value

    for zone_payload in normalize_hr_zone_payloads(payload):
        zone_mapping = as_mapping(zone_payload)
        if extract_zone_number(zone_mapping) == zone_number:
            return extract_zone_duration_from_mapping(zone_mapping)

    return None


def map_time_series(details_payload: object | None) -> list[TimeSeriesPoint]:
    rows = normalize_detail_rows(details_payload)
    if not rows:
        return []

    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return []

    indexed = build_time_indexed_frame(dataframe)
    if indexed.empty:
        return []

    numeric_columns = [
        column
        for column in (
            "distance_m",
            "heart_rate",
            "speed_mps",
            "elevation_m",
            "cadence_spm",
            "power",
        )
        if column in indexed.columns
    ]
    resampled = (
        indexed[numeric_columns]
        .apply(pd.to_numeric, errors="coerce")
        .resample("10s")
        .mean()
        .interpolate(method="linear")
        .ffill()
        .bfill()
    )
    if resampled.empty:
        return []

    first_index = resampled.index[0]
    points: list[TimeSeriesPoint] = []
    for index, row in resampled.iterrows():
        elapsed_seconds = round((index - first_index).total_seconds())
        distance_m = clean_float(row.get("distance_m"))
        speed_mps = clean_float(row.get("speed_mps"))
        pace = speed_mps_to_pace_min_per_km(speed_mps)

        points.append(
            TimeSeriesPoint(
                elapsed_seconds=elapsed_seconds,
                distance_km=meters_to_kilometers(distance_m),
                heart_rate=as_int(clean_float(row.get("heart_rate"))),
                pace_min_per_km=pace,
                elevation_m=round_optional(clean_float(row.get("elevation_m")), 1),
                cadence_spm=round_optional(clean_float(row.get("cadence_spm")), 1),
                power_w=round_optional(clean_float(row.get("power")), 1),
            )
        )

    return points


def normalize_detail_rows(details_payload: object | None) -> list[dict[str, object]]:
    payload = as_mapping(details_payload)
    descriptors = payload.get("metricDescriptors")
    detail_metrics = payload.get("activityDetailMetrics")
    descriptor_map = build_descriptor_map(descriptors)

    if isinstance(detail_metrics, Sequence) and not isinstance(
        detail_metrics,
        str | bytes | bytearray,
    ):
        detail_metric_items = list(detail_metrics)
        logger.debug(
            "Garmin activityDetailMetrics structure: count=%s first=%s",
            len(detail_metric_items),
            detail_metric_items[:2],
        )
        columnar_rows = normalize_columnar_detail_metrics(detail_metric_items, descriptor_map)
        if columnar_rows:
            return columnar_rows

        rows = []
        for detail_metric in detail_metric_items:
            detail_mapping = as_mapping(detail_metric)
            metrics = detail_mapping.get("metrics")
            if descriptor_map and isinstance(metrics, Sequence) and not isinstance(
                metrics,
                str | bytes | bytearray,
            ):
                rows.append(normalize_metric_values(metrics, descriptor_map))
            elif detail_mapping:
                rows.append(normalize_metric_values_from_mapping(detail_mapping))

        return rows

    samples = payload.get("samples") or payload.get("timeSeries")
    if isinstance(samples, Sequence) and not isinstance(samples, str | bytes | bytearray):
        return [
            normalize_metric_values_from_mapping(as_mapping(sample))
            for sample in samples
            if as_mapping(sample)
        ]

    return []


def normalize_columnar_detail_metrics(
    detail_metrics: Sequence[object],
    descriptor_map: Mapping[int, str],
) -> list[dict[str, object]]:
    metric_series_by_key: dict[str, Sequence[object]] = {}
    for detail_metric in detail_metrics:
        detail_mapping = as_mapping(detail_metric)
        metric_index = as_int(
            first_non_null(
                detail_mapping.get("metricsIndex"),
                detail_mapping.get("metricIndex"),
                detail_mapping.get("index"),
            )
        )
        metrics = detail_mapping.get("metrics")
        if (
            metric_index is None
            or metric_index not in descriptor_map
            or not isinstance(metrics, Sequence)
            or isinstance(metrics, str | bytes | bytearray)
        ):
            return []

        metric_series_by_key[descriptor_map[metric_index]] = metrics

    if not metric_series_by_key:
        return []

    sample_count = min(len(series) for series in metric_series_by_key.values())
    if sample_count <= 1:
        return []

    return [
        normalize_metric_values_from_mapping(
            {
                metric_key: metric_series[sample_index]
                for metric_key, metric_series in metric_series_by_key.items()
            }
        )
        for sample_index in range(sample_count)
    ]


def build_descriptor_map(descriptors: object) -> dict[int, str]:
    if not isinstance(descriptors, Sequence) or isinstance(descriptors, str | bytes | bytearray):
        return {}

    descriptor_map: dict[int, str] = {}
    for descriptor in descriptors:
        descriptor_mapping = as_mapping(descriptor)
        metric_index = as_int(
            first_non_null(
                descriptor_mapping.get("metricsIndex"),
                descriptor_mapping.get("metricIndex"),
                descriptor_mapping.get("index"),
            )
        )
        key = as_optional_str(
            descriptor_mapping.get("key")
            or descriptor_mapping.get("metricKey")
            or descriptor_mapping.get("name")
        )
        if metric_index is not None and key is not None:
            descriptor_map[metric_index] = key

    return descriptor_map


def normalize_metric_values(
    metrics: Sequence[object],
    descriptor_map: Mapping[int, str],
) -> dict[str, object]:
    raw_row = {
        descriptor_key: metrics[metric_index]
        for metric_index, descriptor_key in descriptor_map.items()
        if metric_index < len(metrics)
    }
    return normalize_metric_values_from_mapping(raw_row)


def normalize_metric_values_from_mapping(metric_payload: GarminPayload) -> dict[str, object]:
    return {
        "timestamp": first_present(
            metric_payload,
            ("directTimestamp", "timestamp", "sampleTime", "eventTime"),
        ),
        "elapsed_seconds": first_present(
            metric_payload,
            (
                "sumDuration",
                "sumElapsedDuration",
                "elapsedDuration",
                "elapsedSeconds",
                "startTimeInSeconds",
                "startTimeSec",
                "offsetInSeconds",
                "timeOffsetSeconds",
                "directDuration",
                "totalDuration",
                "timerDuration",
            ),
        ),
        "elapsed_milliseconds": first_present(
            metric_payload,
            (
                "elapsedMilliseconds",
                "startTimeInMilliseconds",
                "startTimeMs",
                "offsetInMilliseconds",
                "timeOffsetMs",
            ),
        ),
        "distance_m": first_present(
            metric_payload,
            ("sumDistance", "distance", "totalDistance", "directDistance"),
        ),
        "heart_rate": first_present(
            metric_payload,
            ("directHeartRate", "heartRate", "heart_rate", "heartrate"),
        ),
        "speed_mps": first_present(
            metric_payload,
            ("directSpeed", "speed", "enhancedSpeed", "velocity"),
        ),
        "elevation_m": first_present(
            metric_payload,
            ("directElevation", "elevation", "altitude", "enhancedAltitude"),
        ),
        "cadence_spm": first_present(
            metric_payload,
            ("directRunCadence", "directCadence", "runCadence", "cadence"),
        ),
        "stride_length": first_present(
            metric_payload,
            (
                "averageStrideLength",
                "avgStrideLength",
                "directStrideLength",
                "strideLength",
            ),
        ),
        "vertical_oscillation": first_present(
            metric_payload,
            (
                "averageVerticalOscillation",
                "avgVerticalOscillation",
                "directVerticalOscillation",
                "verticalOscillation",
            ),
        ),
        "ground_contact_time": first_present(
            metric_payload,
            (
                "averageGroundContactTime",
                "avgGroundContactTime",
                "directGroundContactTime",
                "groundContactTime",
            ),
        ),
        "vertical_ratio": first_present(
            metric_payload,
            (
                "averageVerticalRatio",
                "avgVerticalRatio",
                "directVerticalRatio",
                "verticalRatio",
            ),
        ),
        "power": first_present(
            metric_payload,
            ("directPower", "power", "averagePower", "avgPower"),
        ),
    }


def build_time_indexed_frame(dataframe: Any) -> Any:
    indexed = build_elapsed_indexed_frame(dataframe, "elapsed_seconds", "s")
    if not indexed.empty:
        return indexed

    indexed = build_elapsed_indexed_frame(dataframe, "elapsed_milliseconds", "ms")
    if not indexed.empty:
        return indexed

    indexed = build_timestamp_indexed_frame(dataframe)
    if not indexed.empty:
        return indexed

    return pd.DataFrame()


def build_elapsed_indexed_frame(dataframe: Any, column: str, unit: str) -> Any:
    if column not in dataframe.columns:
        return pd.DataFrame()

    numeric_elapsed = pd.to_numeric(dataframe[column], errors="coerce")
    return build_numeric_elapsed_indexed_frame(dataframe, numeric_elapsed, column, unit)


def build_numeric_elapsed_indexed_frame(
    dataframe: Any,
    numeric_elapsed: Any,
    column: str,
    unit: str,
) -> Any:
    if numeric_elapsed.notna().sum() <= 1 or numeric_elapsed.nunique(dropna=True) <= 1:
        return pd.DataFrame()

    logger.info(
        "Garmin time-series index column=%s unit=%s max=%s",
        column,
        unit,
        numeric_elapsed.max(),
    )
    elapsed = pd.to_timedelta(numeric_elapsed, unit=unit)
    indexed = dataframe.assign(elapsed=elapsed).dropna(subset=["elapsed"])
    if indexed.empty:
        return pd.DataFrame()

    return indexed.set_index("elapsed").sort_index()


def build_timestamp_indexed_frame(dataframe: Any) -> Any:
    if "timestamp" not in dataframe.columns:
        return pd.DataFrame()

    numeric_timestamp = pd.to_numeric(dataframe["timestamp"], errors="coerce")
    if numeric_timestamp.notna().sum() > 1 and numeric_timestamp.nunique(dropna=True) > 1:
        max_timestamp = float(numeric_timestamp.max())
        if max_timestamp > 1_000_000_000_000:
            timestamps = pd.to_datetime(numeric_timestamp, unit="ms", errors="coerce")
        elif max_timestamp > 1_000_000_000:
            timestamps = pd.to_datetime(numeric_timestamp, unit="s", errors="coerce")
        else:
            return build_numeric_elapsed_indexed_frame(
                dataframe,
                numeric_timestamp,
                "timestamp",
                "s",
            )

        if timestamps.notna().sum() > 1 and timestamps.nunique(dropna=True) > 1:
            logger.info(
                "Garmin time-series index column=timestamp unit=epoch max=%s",
                max_timestamp,
            )
            indexed = dataframe.assign(timestamp=timestamps).dropna(subset=["timestamp"])
            return indexed.set_index("timestamp").sort_index()

    timestamps = pd.to_datetime(dataframe["timestamp"], errors="coerce")
    if timestamps.notna().sum() > 1 and timestamps.nunique(dropna=True) > 1:
        logger.info(
            "Garmin time-series index column=timestamp unit=datetime max=%s",
            timestamps.max(),
        )
        indexed = dataframe.assign(timestamp=timestamps).dropna(subset=["timestamp"])
        return indexed.set_index("timestamp").sort_index()

    return pd.DataFrame()


def extract_pace(summary_dto: GarminPayload) -> float | None:
    pace = speed_mps_to_pace_min_per_km(as_float(summary_dto.get("averageSpeed")))
    if pace is not None:
        return pace

    return duration_distance_to_pace_min_per_km(
        as_float(summary_dto.get("duration")),
        as_float(summary_dto.get("distance")),
    )


def extract_activity_type(summary_payload: GarminPayload) -> str:
    activity_type = as_mapping(summary_payload.get("activityTypeDTO"))
    type_key = as_optional_str(activity_type.get("typeKey"))
    return type_key or "unknown"


def parse_activity_date(summary_payload: GarminPayload) -> date:
    raw_value = extract_activity_time_value(summary_payload, "start")
    if raw_value is None:
        return date.today()

    parsed = parse_garmin_datetime(raw_value)
    if parsed is not None:
        return parsed.date()

    return date.today()


def extract_activity_time_window(
    summary_payload: GarminPayload,
) -> tuple[datetime | None, datetime | None]:
    start = parse_garmin_datetime(extract_activity_time_value(summary_payload, "start"))
    end = parse_garmin_datetime(extract_activity_time_value(summary_payload, "end"))
    if start is None:
        return None, end

    if end is not None:
        return start, end

    duration_seconds = as_float(as_mapping(summary_payload.get("summaryDTO")).get("duration"))
    if duration_seconds is None:
        return start, None

    return start, start + timedelta(seconds=duration_seconds)


def extract_activity_time_value(summary_payload: GarminPayload, boundary: str) -> object | None:
    summary_dto = as_mapping(summary_payload.get("summaryDTO"))
    if boundary == "end":
        return first_non_null(
            summary_payload.get("endTimeGMT"),
            summary_payload.get("endTimeLocal"),
            summary_payload.get("finishTimeGMT"),
            summary_payload.get("finishTimeLocal"),
            summary_dto.get("endTimeGMT"),
            summary_dto.get("endTimeLocal"),
            summary_dto.get("finishTimeGMT"),
            summary_dto.get("finishTimeLocal"),
        )

    return first_non_null(
        summary_payload.get("startTimeGMT"),
        summary_payload.get("beginTimestamp"),
        summary_payload.get("startTimeLocal"),
        summary_dto.get("startTimeGMT"),
        summary_dto.get("beginTimestamp"),
        summary_dto.get("startTimeLocal"),
    )


def parse_garmin_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return normalize_datetime(value)

    text_value = str(value).strip()
    numeric_value = as_float(value)
    if numeric_value is not None and text_value.replace(".", "", 1).isdigit():
        if numeric_value > 1_000_000_000_000:
            return datetime.fromtimestamp(numeric_value / 1000, tz=UTC).replace(
                tzinfo=None
            )

        if numeric_value > 1_000_000_000:
            return datetime.fromtimestamp(numeric_value, tz=UTC).replace(tzinfo=None)

    raw_text = text_value.replace("Z", "+00:00")
    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw_text, date_format)
        except ValueError:
            continue

    try:
        return normalize_datetime(datetime.fromisoformat(raw_text))
    except ValueError:
        return None


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value

    return value.astimezone(UTC).replace(tzinfo=None)


def extract_weather(summary_payload: GarminPayload) -> str | None:
    weather_dto = as_mapping(summary_payload.get("weatherDTO"))
    return (
        as_optional_str(weather_dto.get("weatherType"))
        or as_optional_str(weather_dto.get("condition"))
        or as_optional_str(summary_payload.get("weather"))
    )


def extract_physiology(
    summary_payload: GarminPayload,
    *,
    daily_stats_payload: object | None = None,
    sleep_payload: object | None = None,
    hrv_payload: object | None = None,
    body_battery_payload: object | None = None,
) -> PhysiologySnapshot:
    summary_dto = as_mapping(summary_payload.get("summaryDTO"))
    physiology = as_mapping(summary_payload.get("physiologyDTO"))
    hrv = as_mapping(summary_payload.get("hrvDTO"))
    dedicated_hrv = as_mapping(hrv_payload).get("hrvSummary")
    dedicated_hrv_mapping = as_mapping(dedicated_hrv)
    body_battery = as_mapping(summary_payload.get("bodyBatteryDTO"))
    activity_start, activity_end = extract_activity_time_window(summary_payload)
    body_battery_start, body_battery_end = extract_body_battery_bounds(
        body_battery_payload,
        activity_start=activity_start,
        activity_end=activity_end,
    )
    body_battery_impact = as_int(
        first_non_null(
            summary_dto.get("differenceBodyBattery"),
            summary_payload.get("differenceBodyBattery"),
            body_battery.get("differenceBodyBattery"),
            physiology.get("differenceBodyBattery"),
        )
    )
    if body_battery_impact is not None:
        body_battery_start = None
        body_battery_end = None
    daily_stats = as_mapping(daily_stats_payload)
    sleep = as_mapping(sleep_payload)
    daily_sleep = as_mapping(sleep.get("dailySleepDTO"))
    sleep_scores = as_mapping(daily_sleep.get("sleepScores"))
    sleep_overall = as_mapping(sleep_scores.get("overall"))

    return PhysiologySnapshot(
        resting_hr=as_int(
            first_non_null(
                physiology.get("restingHR"),
                summary_payload.get("restingHR"),
                daily_stats.get("restingHeartRate"),
                daily_stats.get("restingHR"),
                daily_sleep.get("restingHeartRate"),
            )
        ),
        hrv_status=as_optional_str(
            first_non_null(
                dedicated_hrv_mapping.get("status"),
                hrv.get("status"),
                physiology.get("hrvStatus"),
            )
        ),
        hrv_avg_ms=as_float(
            first_non_null(
                dedicated_hrv_mapping.get("weeklyAvg"),
                dedicated_hrv_mapping.get("lastNightAvg"),
                dedicated_hrv_mapping.get("sevenDayAvg"),
                hrv.get("weeklyAvg"),
                physiology.get("hrvAvgMs"),
            )
        ),
        body_battery_start=as_int(
            first_non_null(
                body_battery_start,
                body_battery.get("start"),
                physiology.get("bodyBatteryStart"),
            )
        ),
        body_battery_end=as_int(
            first_non_null(
                body_battery_end,
                body_battery.get("end"),
                physiology.get("bodyBatteryEnd"),
            )
        ),
        body_battery_impact=body_battery_impact,
        stress_avg=as_int(
            first_non_null(
                physiology.get("stressAvg"),
                summary_payload.get("stressAvg"),
                daily_stats.get("averageStressLevel"),
                daily_stats.get("avgStressLevel"),
            )
        ),
        sleep_score=as_int(
            first_non_null(
                physiology.get("sleepScore"),
                summary_payload.get("sleepScore"),
                sleep.get("sleepScore"),
                daily_sleep.get("sleepScore"),
                sleep_overall.get("value"),
            )
        ),
        recovery_time_hours=as_float(
            normalize_recovery_time_hours(
                first_non_null(
                physiology.get("recoveryTimeHours"),
                physiology.get("recoveryTime"),
                summary_payload.get("recoveryTimeHours"),
                summary_payload.get("recoveryTime"),
                summary_dto.get("recoveryTimeHours"),
                summary_dto.get("recoveryTime"),
            )
            )
        ),
        training_readiness=as_int(
            first_non_null(
                physiology.get("trainingReadiness"),
                summary_payload.get("trainingReadiness"),
                daily_stats.get("trainingReadiness"),
                daily_stats.get("trainingReadinessScore"),
            )
        ),
    )


def as_mapping(value: object) -> GarminPayload:
    if isinstance(value, Mapping):
        return value

    return {}


def first_present(payload: GarminPayload, keys: Sequence[str]) -> object | None:
    for key in keys:
        if key in payload:
            return cast(object, payload[key])

    return None


def first_mapping_from_sequence(value: object | None) -> GarminPayload:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return {}

    for item in value:
        if isinstance(item, Mapping):
            return item

    return {}


def first_non_null(*values: object | None) -> object | None:
    for value in values:
        if value is not None:
            return value

    return None


def extract_body_battery_bounds(
    body_battery_payload: object | None,
    *,
    activity_start: datetime | None = None,
    activity_end: datetime | None = None,
) -> tuple[int | None, int | None]:
    activity_start_ts = datetime_to_epoch_ms(activity_start)
    activity_end_ts = datetime_to_epoch_ms(activity_end)
    bb_data = extract_body_battery_points(body_battery_payload)
    if activity_start_ts is not None and bb_data:
        activity_start_ts = synchronize_epoch_unit(activity_start_ts, bb_data[0][0])
    if activity_end_ts is not None and bb_data:
        activity_end_ts = synchronize_epoch_unit(activity_end_ts, bb_data[0][0])
    if (
        bb_data
        and activity_start_ts is not None
        and activity_end_ts is not None
    ):
        start_point = select_closest_body_battery_point(bb_data, activity_start_ts)
        end_point = select_closest_body_battery_point(bb_data, activity_end_ts)
        start_value = (
            start_point[1]
            if abs(start_point[0] - activity_start_ts) <= BODY_BATTERY_MAX_DELTA_MS
            else None
        )
        end_value = (
            end_point[1]
            if abs(end_point[0] - activity_end_ts) <= BODY_BATTERY_MAX_DELTA_MS
            else None
        )
        return start_value, end_value

    values: list[int] = []
    payloads: list[object]
    if isinstance(body_battery_payload, Sequence) and not isinstance(
        body_battery_payload,
        str | bytes | bytearray,
    ):
        payloads = list(body_battery_payload)
    else:
        payloads = [body_battery_payload]

    for payload in payloads:
        point_value = extract_body_battery_value(payload)
        if point_value is not None:
            values.append(point_value)

        payload_mapping = as_mapping(payload)
        direct_start = as_int(
            payload_mapping.get("start")
            or payload_mapping.get("bodyBatteryStart")
            or payload_mapping.get("startValue")
        )
        direct_end = as_int(
            payload_mapping.get("end")
            or payload_mapping.get("bodyBatteryEnd")
            or payload_mapping.get("endValue")
        )
        if direct_start is not None:
            values.append(direct_start)
        if direct_end is not None:
            values.append(direct_end)

        array_payload = (
            payload_mapping.get("bodyBatteryValuesArray")
            or payload_mapping.get("bodyBatteryValues")
            or payload_mapping.get("values")
        )
        if isinstance(array_payload, Sequence) and not isinstance(
            array_payload,
            str | bytes | bytearray,
        ):
            for entry in array_payload:
                entry_value = extract_body_battery_value(entry)
                if entry_value is not None:
                    values.append(entry_value)

    if not values:
        return None, None

    return values[0], values[-1]


def extract_body_battery_points(
    body_battery_payload: object | None,
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    payloads: list[object]
    if isinstance(body_battery_payload, Sequence) and not isinstance(
        body_battery_payload,
        str | bytes | bytearray,
    ):
        payloads = list(body_battery_payload)
    else:
        payloads = [body_battery_payload]

    for payload in payloads:
        add_body_battery_point(points, payload)
        payload_mapping = as_mapping(payload)
        array_payload = (
            payload_mapping.get("bodyBatteryValuesArray")
            or payload_mapping.get("bodyBatteryValues")
            or payload_mapping.get("values")
        )
        if isinstance(array_payload, Sequence) and not isinstance(
            array_payload,
            str | bytes | bytearray,
        ):
            for entry in array_payload:
                add_body_battery_point(points, entry)

    return sorted(points, key=lambda point: point[0])


def select_closest_body_battery_point(
    points: Sequence[tuple[int, int]],
    target_ms: int,
) -> tuple[int, int]:
    return min(points, key=lambda point: abs(point[0] - target_ms))


def add_body_battery_point(
    points: list[tuple[int, int]],
    entry: object,
) -> None:
    timestamp = extract_body_battery_timestamp(entry)
    value = extract_body_battery_value(entry)
    if timestamp is None or value is None:
        return

    points.append((timestamp, value))


def extract_body_battery_timestamp(entry: object) -> int | None:
    if isinstance(entry, Sequence) and not isinstance(entry, str | bytes | bytearray):
        if len(entry) > 0:
            return value_to_epoch_ms(entry[0])
        return None

    entry_mapping = as_mapping(entry)
    return value_to_epoch_ms(
        first_non_null(
            entry_mapping.get("timestamp"),
            entry_mapping.get("dateTime"),
            entry_mapping.get("startTimeGMT"),
            entry_mapping.get("startTimeLocal"),
            entry_mapping.get("measurementTime"),
        )
    )


def datetime_to_epoch_ms(value: datetime | None) -> int | None:
    if value is None:
        return None

    return int(normalize_datetime(value).replace(tzinfo=UTC).timestamp() * 1000)


def value_to_epoch_ms(value: object | None) -> int | None:
    if value is None:
        return None

    numeric_value = as_float(value)
    if numeric_value is not None and str(value).strip().replace(".", "", 1).isdigit():
        if numeric_value > 1_000_000_000_000:
            return int(numeric_value)
        if numeric_value > 1_000_000_000:
            return int(numeric_value * 1000)

    parsed = parse_garmin_datetime(value)
    if parsed is None:
        return None

    return int(normalize_datetime(parsed).replace(tzinfo=UTC).timestamp() * 1000)


def synchronize_epoch_unit(activity_epoch: int, reference_epoch: int) -> int:
    activity_digits = len(str(abs(activity_epoch)))
    reference_digits = len(str(abs(reference_epoch)))
    if activity_digits == 10 and reference_digits == 13:
        return activity_epoch * 1000
    if activity_digits == 13 and reference_digits == 10:
        return activity_epoch // 1000
    return activity_epoch


def extract_training_load_from_status(training_status: GarminPayload) -> float | None:
    all_training_loads = training_status.get("allTrainingLoads")
    if not isinstance(all_training_loads, Sequence) or isinstance(
        all_training_loads,
        str | bytes | bytearray,
    ):
        return None

    preferred_type_order = ("DAILY", "TOTAL", "ACUTE")
    normalized_items = [as_mapping(item) for item in all_training_loads]

    for preferred_type in preferred_type_order:
        for item in normalized_items:
            item_type = as_optional_str(item.get("type"))
            if item_type is None or item_type.upper() != preferred_type:
                continue

            load_value = as_float(first_non_null(item.get("load"), item.get("value")))
            if load_value is not None:
                return load_value

    for item in normalized_items:
        load_value = as_float(first_non_null(item.get("load"), item.get("value")))
        if load_value is not None:
            return load_value

    return None


def extract_body_battery_value(entry: object) -> int | None:
    if isinstance(entry, Sequence) and not isinstance(entry, str | bytes | bytearray):
        if len(entry) > 1:
            return as_int(entry[1])
        return None

    entry_mapping = as_mapping(entry)
    return as_int(
        entry_mapping.get("value")
        or entry_mapping.get("bodyBattery")
        or entry_mapping.get("bodyBatteryLevel")
    )


def as_optional_str(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def as_float(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if not isinstance(value, str | int | float):
        return None

    try:
        return float(value)
    except ValueError:
        return None


def clean_float(value: object) -> float | None:
    number = as_float(value)
    if number is None or pd.isna(number):
        return None

    return number


def round_optional(value: float | None, precision: int) -> float | None:
    if value is None:
        return None

    return round(value, precision)


def as_int(value: object) -> int | None:
    number = as_float(value)
    if number is None:
        return None

    return round(number)
