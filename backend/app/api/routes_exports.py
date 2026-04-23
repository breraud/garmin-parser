from datetime import UTC, datetime
from io import BytesIO
from typing import Annotated
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.core.auth import AuthenticatedUser, get_current_user
from app.garmin.client import GarminClient
from app.garmin.exceptions import (
    GarminActivityNotFoundError,
    GarminAuthenticationError,
    GarminClientError,
    GarminRateLimitError,
)
from app.garmin.registry import GarminClientRegistry, get_garmin_client_registry
from app.markdown.renderer import MarkdownRenderer
from app.processing.mapper import map_activity, parse_activity_date
from app.schemas.exports import (
    BatchExportRequest,
    MarkdownExportRequest,
    MarkdownExportResponse,
)
from app.schemas.internal import NormalizedActivity

router = APIRouter(prefix="/api/exports", tags=["exports"])


async def get_garmin_client_registry_dependency() -> GarminClientRegistry:
    return get_garmin_client_registry()


async def get_garmin_client(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    registry: Annotated[
        GarminClientRegistry,
        Depends(get_garmin_client_registry_dependency),
    ],
) -> GarminClient:
    return registry.get_client(current_user.email_hash)


async def get_markdown_renderer() -> MarkdownRenderer:
    return MarkdownRenderer()


@router.post("/markdown", response_model=MarkdownExportResponse)
async def export_markdown(
    request: MarkdownExportRequest,
    garmin_client: Annotated[GarminClient, Depends(get_garmin_client)],
    renderer: Annotated[MarkdownRenderer, Depends(get_markdown_renderer)],
) -> MarkdownExportResponse:
    if request.mode != "single_activity":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only single_activity exports are supported by the MVP endpoint.",
        )

    if request.activity_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="activity_id is required.",
        )

    try:
        garmin_client.ensure_authenticated()
        activity = fetch_and_map_activity(garmin_client, request.activity_id)
        markdown = renderer.render_activity(activity, notes=request.notes)
    except GarminAuthenticationError as exc:
        raise_garmin_http_exception(exc)
    except GarminActivityNotFoundError as exc:
        raise_garmin_http_exception(exc)
    except GarminRateLimitError as exc:
        raise_garmin_http_exception(exc)
    except GarminClientError as exc:
        raise_garmin_http_exception(exc)

    return MarkdownExportResponse(
        status="success",
        markdown=markdown,
        metadata={
            "activity_count": 1,
            "generated_at": datetime.now(UTC).isoformat(),
        },
    )


@router.post("/batch-markdown", response_model=MarkdownExportResponse)
async def export_batch_markdown(
    request: MarkdownExportRequest,
    garmin_client: Annotated[GarminClient, Depends(get_garmin_client)],
    renderer: Annotated[MarkdownRenderer, Depends(get_markdown_renderer)],
) -> MarkdownExportResponse:
    if request.mode != "date_range":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="batch-markdown requires date_range mode.",
        )

    if request.date_from is None or request.date_to is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from and date_to are required.",
        )

    try:
        garmin_client.ensure_authenticated()
        activity_refs = garmin_client.list_running_activities(
            request.date_from,
            request.date_to,
            request.max_activities,
        )[: request.max_activities]
        activities = []
        for activity_ref in activity_refs:
            activity_id = extract_activity_id(activity_ref)
            activities.append(fetch_and_map_activity(garmin_client, activity_id))

        markdown = renderer.render_batch(activities, notes=request.notes)
    except GarminAuthenticationError as exc:
        raise_garmin_http_exception(exc)
    except GarminActivityNotFoundError as exc:
        raise_garmin_http_exception(exc)
    except GarminRateLimitError as exc:
        raise_garmin_http_exception(exc)
    except GarminClientError as exc:
        raise_garmin_http_exception(exc)

    return MarkdownExportResponse(
        status="success",
        markdown=markdown,
        metadata={
            "activity_count": len(activities),
            "generated_at": datetime.now(UTC).isoformat(),
            "date_from": request.date_from.isoformat(),
            "date_to": request.date_to.isoformat(),
        },
    )


@router.post("/batch")
async def export_batch_zip(
    request: BatchExportRequest,
    garmin_client: Annotated[GarminClient, Depends(get_garmin_client)],
    renderer: Annotated[MarkdownRenderer, Depends(get_markdown_renderer)],
) -> Response:
    try:
        garmin_client.ensure_authenticated()
        rendered_activities: list[tuple[NormalizedActivity, str]] = []
        for activity_id in request.activity_ids:
            activity = fetch_and_map_activity(garmin_client, activity_id)
            markdown = renderer.render_activity(activity, notes=request.notes)
            rendered_activities.append((activity, markdown))

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        if request.export_format == "markdown":
            content = "\n\n---\n\n".join(markdown.rstrip() for _, markdown in rendered_activities)
            return Response(
                content=content + "\n",
                media_type="text/markdown; charset=utf-8",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="garmin-batch-{timestamp}.md"'
                    )
                },
            )

        archive_buffer = BytesIO()
        with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
            for activity, markdown in rendered_activities:
                archive.writestr(build_markdown_filename(activity), markdown)
    except GarminAuthenticationError as exc:
        raise_garmin_http_exception(exc)
    except GarminActivityNotFoundError as exc:
        raise_garmin_http_exception(exc)
    except GarminRateLimitError as exc:
        raise_garmin_http_exception(exc)
    except GarminClientError as exc:
        raise_garmin_http_exception(exc)

    archive_bytes = archive_buffer.getvalue()
    headers = {
        "Content-Disposition": f'attachment; filename="garmin-batch-{timestamp}.zip"'
    }
    return Response(
        content=archive_bytes,
        media_type="application/zip",
        headers=headers,
    )

def extract_activity_id(activity_ref: dict[str, object]) -> str:
    raw_activity_id = activity_ref.get("activityId") or activity_ref.get("activity_id")
    if raw_activity_id is None:
        raise GarminActivityNotFoundError("Garmin activity reference has no activity ID.")

    return str(raw_activity_id)


def fetch_and_map_activity(garmin_client: GarminClient, activity_id: str) -> NormalizedActivity:
    activity_payload = garmin_client.get_activity(activity_id)
    activity_date = parse_activity_date(activity_payload)
    splits_payload = garmin_client.get_activity_splits(activity_id)
    details_payload = garmin_client.get_activity_details(activity_id)
    hr_zones_payload = garmin_client.get_activity_hr_zones(activity_id)
    daily_stats_payload = garmin_client.get_daily_stats(activity_date)
    training_status_payload = garmin_client.get_training_status(activity_date)
    stats_and_body_composition_payload = garmin_client.get_stats_and_body_composition(
        activity_date
    )
    sleep_payload = garmin_client.get_sleep_data(activity_date)
    hrv_payload = garmin_client.get_hrv_data(activity_date)
    body_battery_payload = garmin_client.get_body_battery(activity_date)

    return map_activity(
        activity_payload,
        splits_payload,
        details_payload=details_payload,
        hr_zones_payload=hr_zones_payload,
        daily_stats_payload=daily_stats_payload,
        training_status_payload=training_status_payload,
        stats_and_body_composition_payload=stats_and_body_composition_payload,
        sleep_payload=sleep_payload,
        hrv_payload=hrv_payload,
        body_battery_payload=body_battery_payload,
    )


def build_markdown_filename(activity: NormalizedActivity) -> str:
    return f"{activity.summary.date.isoformat()}-{activity.summary.activity_id}.md"


def raise_garmin_http_exception(exc: GarminClientError) -> None:
    if isinstance(exc, GarminAuthenticationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Garmin authentication failed.",
        ) from exc

    if isinstance(exc, GarminActivityNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Garmin activity was not found.",
        ) from exc

    if isinstance(exc, GarminRateLimitError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Garmin rate limit reached. Retry later.",
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Garmin request failed.",
    ) from exc
