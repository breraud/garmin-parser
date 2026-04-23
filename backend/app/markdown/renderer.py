import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from app.schemas.internal import NormalizedActivity

SCHEMA_VERSION = "1.2"
logger = logging.getLogger(__name__)


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "Non disponible"

    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"


def format_duration_compact(seconds: int | None) -> str:
    if seconds is None:
        return "-"

    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"

    return f"{minutes:02d}:{remaining_seconds:02d}"


def format_pace(minutes_per_km: float | None) -> str:
    if minutes_per_km is None:
        return "Non disponible"

    minutes = int(minutes_per_km)
    seconds = round((minutes_per_km - minutes) * 60)
    if seconds == 60:
        minutes += 1
        seconds = 0

    return f"{minutes}:{seconds:02d}/km"


def format_pace_compact(minutes_per_km: float | None) -> str:
    if minutes_per_km is None:
        return "-"

    return format_pace(minutes_per_km)


def compact_number(value: float | int | None, precision: int = 1) -> str:
    if value is None:
        return "Non disponible"

    if isinstance(value, int):
        return str(value)

    rounded = round(value, precision)
    if rounded.is_integer():
        return str(int(rounded))

    return f"{rounded:.{precision}f}"


def compact_token(value: float | int | str | None, precision: int = 1) -> str:
    if value is None:
        return "-"

    if isinstance(value, str):
        return value

    return compact_number(value, precision)


def format_distance(value: float | None) -> str:
    if value is None:
        return "Non disponible"

    return f"{value:.2f} km"


def format_distance_token(value: float | None, precision: int = 2) -> str:
    if value is None:
        return "-"

    return f"{value:.{precision}f}"


def format_meters(value: float | None) -> str:
    if value is None:
        return "Non disponible"

    return f"{round(value)} m"


def format_meters_token(value: float | None) -> str:
    if value is None:
        return "-"

    return f"{round(value)} m"


def format_optional(value: Any, suffix: str = "") -> str:
    if value is None:
        return "Non disponible"

    return f"{value}{suffix}"


def extract_garmin_description(activity: NormalizedActivity) -> str | None:
    source_payload = activity.source_payload or {}
    description = source_payload.get("description")
    if description is None:
        metadata_dto = source_payload.get("metadataDTO")
        if isinstance(metadata_dto, dict):
            description = metadata_dto.get("notes")
    if description is None:
        description = source_payload.get("activityDescription")
    if description is None:
        description = source_payload.get("comments")
    if description is None:
        summary_dto = source_payload.get("summaryDTO")
        if isinstance(summary_dto, dict):
            description = summary_dto.get("comments")

    if description is None:
        source_keys = sorted(source_payload.keys())
        logger.debug("Garmin notes unavailable; source payload keys: %s", source_keys)
        summary_dto = source_payload.get("summaryDTO")
        if isinstance(summary_dto, dict):
            logger.debug(
                "Garmin notes unavailable; summaryDTO keys: %s",
                sorted(summary_dto.keys()),
            )
        return None

    text = str(description).strip()
    if not text:
        source_keys = sorted(source_payload.keys())
        logger.debug("Garmin notes empty; source payload keys: %s", source_keys)
        summary_dto = source_payload.get("summaryDTO")
        if isinstance(summary_dto, dict):
            logger.debug(
                "Garmin notes empty; summaryDTO keys: %s",
                sorted(summary_dto.keys()),
            )
    return text or None


class MarkdownRenderer:
    def __init__(self, template_dir: Path | None = None) -> None:
        resolved_template_dir = template_dir or Path(__file__).parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(str(resolved_template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["duration"] = format_duration
        self._env.filters["duration_compact"] = format_duration_compact
        self._env.filters["pace"] = format_pace
        self._env.filters["pace_compact"] = format_pace_compact
        self._env.filters["compact_number"] = compact_number
        self._env.filters["compact_token"] = compact_token
        self._env.filters["distance"] = format_distance
        self._env.filters["distance_token"] = format_distance_token
        self._env.filters["meters"] = format_meters
        self._env.filters["meters_token"] = format_meters_token
        self._env.filters["optional"] = format_optional

    def render_activity(self, activity: NormalizedActivity, notes: str | None = None) -> str:
        template = self._env.get_template("activity.md.j2")
        resolved_notes = notes or extract_garmin_description(activity)
        return template.render(
            activity=activity,
            notes=resolved_notes,
            schema_version=SCHEMA_VERSION,
        ).strip() + "\n"

    def render_batch(
        self,
        activities: Sequence[NormalizedActivity],
        notes: str | None = None,
    ) -> str:
        template = self._env.get_template("batch.md.j2")
        sorted_activities = sorted(activities, key=lambda activity: activity.summary.date)
        total_distance_km = sum(
            activity.summary.distance_km or 0 for activity in sorted_activities
        )
        total_duration_seconds = sum(
            activity.summary.duration_seconds or 0 for activity in sorted_activities
        )

        return template.render(
            activities=sorted_activities,
            activity_count=len(sorted_activities),
            total_distance_km=total_distance_km,
            total_duration_seconds=total_duration_seconds,
            notes=notes,
            schema_version=SCHEMA_VERSION,
        ).strip() + "\n"
