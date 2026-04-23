import logging
from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import AuthenticatedUser, get_current_user
from app.api.routes_exports import (
    get_garmin_client,
    raise_garmin_http_exception,
)
from app.garmin.client import GarminClient
from app.garmin.exceptions import GarminClientError
from app.processing.mapper import parse_activity_date
from app.processing.metrics import meters_to_kilometers
from app.schemas.activities import ActivitySummary

router = APIRouter(prefix="/api/activities", tags=["activities"])
logger = logging.getLogger(__name__)


@router.get("/recent", response_model=list[ActivitySummary])
async def list_recent_activities(
    _current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    garmin_client: Annotated[GarminClient, Depends(get_garmin_client)],
) -> list[ActivitySummary]:
    try:
        garmin_client.ensure_authenticated()
        activities = garmin_client.get_activities(0, 10)
    except GarminClientError as exc:
        raise_garmin_http_exception(exc)

    logger.debug("DEBUG: Garmin returned %s activities", len(activities))
    recent_running_activities: list[ActivitySummary] = []
    for activity in activities:
        if not is_running_activity(activity):
            continue

        activity_id = activity.get("activityId")
        if activity_id is None:
            continue

        recent_running_activities.append(
            ActivitySummary(
                activity_id=str(activity_id),
                date=parse_activity_date(activity),
                title=str(activity.get("activityName") or "").strip() or None,
                distance_km=meters_to_kilometers(
                    float(activity["distance"]) if activity.get("distance") is not None else None
                ),
            )
        )

    return recent_running_activities


def is_running_activity(activity: dict[str, object]) -> bool:
    activity_type = str(activity.get("activityType") or "").strip().lower()
    activity_type_dto = activity.get("activityTypeDTO")
    dto_type_mapping = activity_type_dto if isinstance(activity_type_dto, Mapping) else {}
    dto_type = str(dto_type_mapping.get("typeKey", "")).strip().lower()
    combined = " ".join(part for part in (activity_type, dto_type) if part)
    return "run" in combined
