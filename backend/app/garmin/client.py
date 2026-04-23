import logging
import os
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import date
from time import monotonic, sleep
from typing import Any, Protocol, TypeVar
from uuid import uuid4

from garminconnect import (  # type: ignore[import-untyped]
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from app.core.auth import hash_email
from app.garmin.cache import ActivityCache
from app.garmin.exceptions import (
    GarminActivityNotFoundError,
    GarminAuthenticationError,
    GarminClientError,
    GarminConnectionError,
    GarminMFARequiredError,
    GarminRateLimitError,
)

GarminSplitsPayload = dict[str, Any] | list[dict[str, Any]]
DateLike = date | str
SessionDataPath = str | os.PathLike[str]
T = TypeVar("T")
logger = logging.getLogger(__name__)
DEFAULT_SESSION_DATA_DIR = os.path.join(os.path.dirname(__file__), "session_data")


class GarminApi(Protocol):
    def login(self, tokenstore: str | None = None) -> tuple[str | None, str | None]: ...

    def get_activity(self, activity_id: str) -> dict[str, Any]: ...

    def get_activity_splits(self, activity_id: str) -> GarminSplitsPayload: ...

    def get_activity_typed_splits(self, activity_id: str) -> GarminSplitsPayload: ...

    def get_activity_details(self, activity_id: str) -> dict[str, Any]: ...

    def get_activity_hr_in_timezones(self, activity_id: str) -> dict[str, Any]: ...

    def get_user_summary(self, cdate: str) -> dict[str, Any]: ...

    def get_training_status(self, cdate: str) -> dict[str, Any]: ...

    def get_stats_and_body_composition(self, cdate: str) -> dict[str, Any]: ...

    def get_sleep_data(self, cdate: str) -> dict[str, Any]: ...

    def get_hrv_data(self, cdate: str) -> dict[str, Any] | None: ...

    def get_body_battery(
        self,
        startdate: str,
        enddate: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_activities_by_date(
        self,
        startdate: str,
        enddate: str,
        activitytype: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class GarminSession:
    session_id: str
    authenticated: bool
    mfa_required: bool = False


class GarminClient:
    def __init__(
        self,
        api: GarminApi | None = None,
        email: str | None = None,
        password: str | None = None,
        cache: ActivityCache | None = None,
        min_request_interval_seconds: float = 2.0,
        secondary_request_delay_seconds: float = 1.0,
        request_timeout_seconds: float = 15.0,
        session_data_dir: SessionDataPath | None = None,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._api = api
        self._email = email
        self._password = password
        self._cache = cache or ActivityCache(ttl_seconds=900)
        self._min_request_interval_seconds = min_request_interval_seconds
        self._secondary_request_delay_seconds = secondary_request_delay_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._session_data_dir = os.fspath(session_data_dir or DEFAULT_SESSION_DATA_DIR)
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self._pending_credentials: tuple[str | None, str | None] | None = None
        os.makedirs(self._session_data_dir, exist_ok=True)

    def login(self, email: str, password: str) -> GarminSession:
        self._email = email
        self._password = password
        return self.ensure_authenticated(force_refresh=True)

    def ensure_authenticated(self, force_refresh: bool = False) -> GarminSession:
        if self._api is not None and not force_refresh:
            return GarminSession(session_id=self._new_session_id(), authenticated=True)

        api = Garmin(email=self._email, password=self._password, return_on_mfa=True)
        self._configure_api_timeout(api)
        session_data_dir = self._resolve_session_data_dir(
            hash_email(self._email) if self._email is not None else None
        )

        try:
            mfa_status, _legacy_token = self._call_with_timeout(
                "Garmin login",
                lambda: api.login(tokenstore=session_data_dir),
            )
        except Exception as exc:
            raise self._map_exception(exc) from exc

        if mfa_status:
            self._pending_credentials = (self._email, self._password)
            self._api = api
            raise GarminMFARequiredError("Garmin requires a verification code.")

        self._api = api
        self._pending_credentials = None
        return GarminSession(session_id=self._new_session_id(), authenticated=True)

    def complete_mfa(self, session_id: str, code: str) -> GarminSession:
        if self._pending_credentials is None:
            raise GarminAuthenticationError("No Garmin MFA challenge is pending.")

        email, password = self._pending_credentials
        if email is None or password is None:
            raise GarminAuthenticationError("Garmin credentials are not available for MFA.")
        api = Garmin(email=email, password=password, prompt_mfa=lambda: code)
        self._configure_api_timeout(api)
        session_data_dir = self._resolve_session_data_dir(hash_email(email))

        try:
            self._call_with_timeout(
                "Garmin MFA login",
                lambda: api.login(tokenstore=session_data_dir),
            )
        except Exception as exc:
            raise self._map_exception(exc) from exc

        self._api = api
        self._pending_credentials = None
        return GarminSession(session_id=session_id, authenticated=True)

    def logout(self, email: str) -> None:
        session_data_dir = self._resolve_session_data_dir(hash_email(email), create=False)
        if os.path.isdir(session_data_dir):
            shutil.rmtree(session_data_dir)

        if self._email is not None and self._email.strip().lower() == email.strip().lower():
            self._api = None
            self._pending_credentials = None
            self._email = None
            self._password = None

    def logout_by_email_hash(self, email_hash: str) -> None:
        session_data_dir = self._resolve_session_data_dir(email_hash, create=False)
        if os.path.isdir(session_data_dir):
            shutil.rmtree(session_data_dir)

        self._api = None
        self._pending_credentials = None
        self._email = None
        self._password = None

    def get_activity(self, activity_id: str) -> dict[str, Any]:
        cache_key = f"activity:{activity_id}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        api = self._require_api()
        self._wait_for_rate_limit()

        try:
            payload = self._call_with_timeout(
                "Garmin get_activity",
                lambda: api.get_activity(activity_id),
            )
        except Exception as exc:
            raise self._map_exception(exc) from exc

        self._cache.set(cache_key, payload)
        return payload

    def get_training_status(self, activity_date: DateLike) -> dict[str, Any]:
        cdate = self._date_key(activity_date)
        cache_key = f"training_status:{cdate}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        api = self._require_api()
        self._wait_for_secondary_request()

        try:
            payload = self._call_with_timeout(
                "Garmin get_training_status",
                lambda: api.get_training_status(cdate),
            )
        except Exception as exc:
            logger.warning(
                "Impossible de récupérer le statut d'entraînement Garmin du %s: %s",
                cdate,
                exc,
            )
            return {}

        self._cache.set(cache_key, payload)
        return payload

    def get_stats_and_body_composition(self, activity_date: DateLike) -> dict[str, Any]:
        cdate = self._date_key(activity_date)
        cache_key = f"stats_and_body_composition:{cdate}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        api = self._require_api()
        get_stats = getattr(api, "get_stats_and_body_composition", None)
        if not callable(get_stats):
            return {}

        self._wait_for_secondary_request()

        try:
            payload = self._call_with_timeout(
                "Garmin get_stats_and_body_composition",
                lambda: get_stats(cdate),
            )
        except Exception as exc:
            logger.warning(
                "Impossible de récupérer les stats globales Garmin du %s: %s",
                cdate,
                exc,
            )
            return {}

        if not isinstance(payload, dict):
            return {}

        self._cache.set(cache_key, payload)
        return payload

    def get_activity_splits(self, activity_id: str) -> GarminSplitsPayload:
        cache_key = f"activity_splits:{activity_id}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict | list):
            return cached

        api = self._require_api()
        self._wait_for_rate_limit()

        try:
            payload = self._call_with_timeout(
                "Garmin get_activity_splits",
                lambda: api.get_activity_splits(activity_id),
            )
        except Exception as exc:
            raise self._map_exception(exc) from exc

        merged_payload = self._merge_typed_split_payloads(api, activity_id, payload)
        self._cache.set(cache_key, merged_payload)
        return merged_payload

    def get_activity_details(self, activity_id: str) -> dict[str, Any]:
        cache_key = f"activity_details:{activity_id}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        api = self._require_api()
        self._wait_for_secondary_request()

        try:
            payload = self._call_with_timeout(
                "Garmin get_activity_details",
                lambda: api.get_activity_details(activity_id),
            )
        except Exception as exc:
            logger.warning(
                "Impossible de récupérer les détails de l'activité Garmin %s: %s",
                activity_id,
                exc,
            )
            return {}

        self._cache.set(cache_key, payload)
        return payload

    def get_activity_hr_zones(self, activity_id: str) -> dict[str, Any]:
        cache_key = f"activity_hr_zones:{activity_id}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        api = self._require_api()
        self._wait_for_secondary_request()

        try:
            payload = self._call_with_timeout(
                "Garmin get_activity_hr_in_timezones",
                lambda: api.get_activity_hr_in_timezones(activity_id),
            )
        except Exception as exc:
            logger.warning(
                "Impossible de récupérer les zones FC Garmin pour l'activité %s: %s",
                activity_id,
                exc,
            )
            return {}

        self._cache.set(cache_key, payload)
        return payload

    def get_daily_stats(self, activity_date: DateLike) -> dict[str, Any]:
        cdate = self._date_key(activity_date)
        cache_key = f"daily_stats:{cdate}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        api = self._require_api()
        self._wait_for_secondary_request()

        try:
            payload = self._call_with_timeout(
                "Garmin get_user_summary",
                lambda: api.get_user_summary(cdate),
            )
        except Exception as exc:
            logger.warning(
                "Impossible de récupérer les statistiques journalières Garmin du %s: %s",
                cdate,
                exc,
            )
            return {}

        self._cache.set(cache_key, payload)
        return payload

    def get_sleep_data(self, activity_date: DateLike) -> dict[str, Any]:
        cdate = self._date_key(activity_date)
        cache_key = f"sleep_data:{cdate}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        api = self._require_api()
        self._wait_for_secondary_request()

        try:
            payload = self._call_with_timeout(
                "Garmin get_sleep_data",
                lambda: api.get_sleep_data(cdate),
            )
        except Exception as exc:
            logger.warning(
                "Impossible de récupérer les données de sommeil Garmin du %s: %s",
                cdate,
                exc,
            )
            return {}

        self._cache.set(cache_key, payload)
        return payload

    def get_hrv_data(self, activity_date: DateLike) -> dict[str, Any]:
        cdate = self._date_key(activity_date)
        cache_key = f"hrv_data:{cdate}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        api = self._require_api()
        self._wait_for_secondary_request()

        try:
            payload = self._call_with_timeout(
                "Garmin get_hrv_data",
                lambda: api.get_hrv_data(cdate) or {},
            )
        except Exception as exc:
            logger.warning(
                "Impossible de récupérer les données HRV Garmin du %s: %s",
                cdate,
                exc,
            )
            return {}

        self._cache.set(cache_key, payload)
        return payload

    def get_body_battery(self, activity_date: DateLike) -> list[dict[str, Any]]:
        cdate = self._date_key(activity_date)
        cache_key = f"body_battery:{cdate}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, list):
            return cached

        api = self._require_api()
        self._wait_for_secondary_request()

        try:
            payload = self._call_with_timeout(
                "Garmin get_body_battery",
                lambda: api.get_body_battery(cdate),
            )
        except Exception as exc:
            logger.warning(
                "Impossible de récupérer le Body Battery Garmin du %s: %s",
                cdate,
                exc,
            )
            return []

        self._cache.set(cache_key, payload)
        return payload

    def list_running_activities(
        self,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> list[dict[str, Any]]:
        api = self._require_api()
        self._wait_for_rate_limit()

        try:
            activities = self._call_with_timeout(
                "Garmin get_activities_by_date",
                lambda: api.get_activities_by_date(
                    date_from.isoformat(),
                    date_to.isoformat(),
                    activitytype="running",
                ),
            )
        except Exception as exc:
            raise self._map_exception(exc) from exc

        return activities[:limit]

    def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        api = self._require_api()
        self._wait_for_rate_limit()

        try:
            return self._call_with_timeout(
                "Garmin get_activities",
                lambda: api.get_activities(start, limit),
            )
        except Exception as exc:
            raise self._map_exception(exc) from exc

    def _require_api(self) -> GarminApi:
        if self._api is None:
            self.ensure_authenticated()

        if self._api is None:
            raise GarminAuthenticationError("Garmin client is not authenticated.")

        return self._api

    def _wait_for_rate_limit(self) -> None:
        now = self._clock()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            remaining = self._min_request_interval_seconds - elapsed
            if remaining > 0:
                self._sleeper(remaining)

        self._last_request_at = self._clock()

    def _wait_for_secondary_request(self) -> None:
        if self._secondary_request_delay_seconds > 0:
            self._sleeper(self._secondary_request_delay_seconds)

        self._wait_for_rate_limit()

    def _new_session_id(self) -> str:
        return uuid4().hex

    def _resolve_session_data_dir(self, email_hash: str | None, *, create: bool = True) -> str:
        if email_hash is None:
            if create:
                os.makedirs(self._session_data_dir, exist_ok=True)
            return self._session_data_dir

        session_path = os.path.join(self._session_data_dir, email_hash)
        if create:
            os.makedirs(session_path, exist_ok=True)
        return session_path

    def _date_key(self, activity_date: DateLike) -> str:
        if isinstance(activity_date, date):
            return activity_date.isoformat()

        return activity_date

    def _call_with_timeout(
        self,
        operation_name: str,
        operation: Callable[[], T],
    ) -> T:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="garmin-api")
        future = executor.submit(operation)
        try:
            return future.result(timeout=self._request_timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise GarminConnectionError(
                f"Garmin request timed out during {operation_name} "
                f"after {self._request_timeout_seconds:g}s."
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _configure_api_timeout(self, api: GarminApi) -> None:
        garth_client = getattr(api, "client", None)
        configure = getattr(garth_client, "configure", None)
        if not callable(configure):
            return

        try:
            configure(timeout=max(1, int(self._request_timeout_seconds)))
        except Exception as exc:
            logger.warning("Impossible de configurer le timeout Garmin: %s", exc)

    def _merge_typed_split_payloads(
        self,
        api: GarminApi,
        activity_id: str,
        base_payload: GarminSplitsPayload,
    ) -> GarminSplitsPayload:
        typed_getter = getattr(api, "get_activity_typed_splits", None)
        if not callable(typed_getter):
            return base_payload

        try:
            typed_payload = self._call_with_timeout(
                "Garmin get_activity_typed_splits",
                lambda: typed_getter(activity_id),
            )
        except Exception as exc:
            logger.warning(
                "Impossible de récupérer les splits typés Garmin pour l'activité %s: %s",
                activity_id,
                exc,
            )
            return base_payload

        if not isinstance(typed_payload, dict):
            return base_payload

        merged_payload: dict[str, Any]
        if isinstance(base_payload, dict):
            merged_payload = dict(base_payload)
        else:
            merged_payload = {"lapDTOs": base_payload}

        for key in (
            "activityIntervals",
            "activityIntervalDTOs",
            "intervals",
            "intervalDTOs",
            "workoutStepDTOs",
            "splitSummaries",
        ):
            typed_value = typed_payload.get(key)
            if typed_value is None:
                continue

            existing_value = merged_payload.get(key)
            if existing_value in (None, [], {}):
                merged_payload[key] = typed_value

        return merged_payload

    def _map_exception(self, exc: Exception) -> GarminClientError:
        message = str(exc)
        lowered = message.lower()

        if isinstance(exc, GarminClientError):
            return exc

        if isinstance(exc, GarminConnectTooManyRequestsError) or any(
            indicator in lowered
            for indicator in ("429", "rate limit", "rate limited", "too many requests")
        ):
            return GarminRateLimitError("Garmin rate limit reached.")

        if isinstance(exc, GarminConnectAuthenticationError) or any(
            indicator in lowered for indicator in ("unauthorized", "authentication", "401")
        ):
            return GarminAuthenticationError("Garmin authentication failed.")

        if "not found" in lowered or "404" in lowered:
            return GarminActivityNotFoundError("Garmin activity was not found.")

        if isinstance(exc, GarminConnectConnectionError):
            return GarminConnectionError("Garmin connection failed.")

        return GarminConnectionError(f"Garmin request failed: {message}")
