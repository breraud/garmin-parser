from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActivitySummary(BaseModel):
    activity_id: str = Field(min_length=1)
    date: date
    activity_type: str = Field(min_length=1)
    title: str | None = None
    distance_km: float | None = Field(default=None, ge=0)
    duration_seconds: int | None = Field(default=None, ge=0)
    moving_duration_seconds: int | None = Field(default=None, ge=0)
    average_pace_min_per_km: float | None = Field(default=None, ge=0)
    average_hr: int | None = Field(default=None, ge=0)
    max_hr: int | None = Field(default=None, ge=0)
    training_load: float | None = Field(default=None, ge=0)
    fitness_state: str | None = None
    training_effect_aerobic: float | None = Field(default=None, ge=0)
    training_effect_anaerobic: float | None = Field(default=None, ge=0)
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    calories: int | None = Field(default=None, ge=0)
    vo2max: float | None = Field(default=None, ge=0)
    perceived_effort: str | None = None
    weather: str | None = None
    avg_power: float | None = Field(default=None, ge=0)
    max_power: float | None = Field(default=None, ge=0)
    avg_stride_length: float | None = Field(default=None, ge=0)
    avg_vertical_ratio: float | None = Field(default=None, ge=0)
    avg_vertical_oscillation: float | None = Field(default=None, ge=0)
    avg_ground_contact_time: float | None = Field(default=None, ge=0)
    start_stamina: float | None = Field(default=None, ge=0)
    end_stamina: float | None = Field(default=None, ge=0)
    min_stamina: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="ignore")


class PhysiologySnapshot(BaseModel):
    resting_hr: int | None = Field(default=None, ge=0)
    hrv_status: str | None = None
    hrv_avg_ms: float | None = Field(default=None, ge=0)
    body_battery_start: int | None = Field(default=None, ge=0, le=100)
    body_battery_end: int | None = Field(default=None, ge=0, le=100)
    body_battery_impact: int | None = None
    stress_avg: int | None = Field(default=None, ge=0)
    sleep_score: int | None = Field(default=None, ge=0, le=100)
    recovery_time_hours: float | None = Field(default=None, ge=0)
    training_readiness: int | None = Field(default=None, ge=0, le=100)

    model_config = ConfigDict(extra="ignore")


class Split(BaseModel):
    index: int = Field(ge=1)
    step_type: str = Field(default="Course", min_length=1)
    distance_km: float = Field(ge=0)
    duration_seconds: int | None = Field(default=None, ge=0)
    pace_min_per_km: float | None = Field(default=None, ge=0)
    average_hr: int | None = Field(default=None, ge=0)
    max_hr: int | None = Field(default=None, ge=0)
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    cadence_spm: float | None = Field(default=None, ge=0)
    stride_length_m: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="ignore")


class HeartRateZone(BaseModel):
    zone: str = Field(pattern=r"^Z[1-5]$")
    duration_seconds: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="ignore")


class TimeSeriesPoint(BaseModel):
    elapsed_seconds: int = Field(ge=0)
    distance_km: float | None = Field(default=None, ge=0)
    heart_rate: int | None = Field(default=None, ge=0)
    pace_min_per_km: float | None = Field(default=None, ge=0)
    elevation_m: float | None = None
    cadence_spm: float | None = Field(default=None, ge=0)
    power_w: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="ignore")


class NormalizedActivity(BaseModel):
    summary: ActivitySummary
    physiology: PhysiologySnapshot = Field(default_factory=PhysiologySnapshot)
    splits: list[Split] = Field(default_factory=list)
    heart_rate_zones: list[HeartRateZone] = Field(default_factory=list)
    time_series: list[TimeSeriesPoint] = Field(default_factory=list)
    source_payload: dict[str, Any] | None = None

    model_config = ConfigDict(extra="ignore")
