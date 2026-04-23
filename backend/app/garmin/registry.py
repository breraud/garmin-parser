import os
import shutil
from functools import lru_cache

from app.core.config import get_settings
from app.garmin.cache import ActivityCache
from app.garmin.client import DEFAULT_SESSION_DATA_DIR, GarminClient


class GarminClientRegistry:
    def __init__(self) -> None:
        settings = get_settings()
        self._cache_ttl_seconds = settings.garmin_cache_ttl_seconds
        self._min_request_interval_seconds = settings.garmin_min_request_interval_seconds
        self._session_data_dir = DEFAULT_SESSION_DATA_DIR
        self._clients: dict[str, GarminClient] = {}

    def get_client(self, email_hash: str) -> GarminClient:
        client = self._clients.get(email_hash)
        if client is not None:
            return client

        client = GarminClient(
            cache=ActivityCache(ttl_seconds=self._cache_ttl_seconds),
            min_request_interval_seconds=self._min_request_interval_seconds,
        )
        self._clients[email_hash] = client
        return client

    def logout(self, email_hash: str) -> None:
        client = self._clients.pop(email_hash, None)
        if client is not None:
            client.logout_by_email_hash(email_hash)
            return

        session_data_dir = os.path.join(self._session_data_dir, email_hash)
        if os.path.isdir(session_data_dir):
            shutil.rmtree(session_data_dir)


@lru_cache
def get_garmin_client_registry() -> GarminClientRegistry:
    return GarminClientRegistry()
