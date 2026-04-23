from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class CacheEntry:
    value: Any
    expires_at: float


class ActivityCache:
    def __init__(
        self,
        ttl_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None

        if entry.expires_at <= self._clock():
            self._entries.pop(key, None)
            return None

        return entry.value

    def set(self, key: str, value: Any) -> None:
        self._entries[key] = CacheEntry(
            value=value,
            expires_at=self._clock() + self._ttl_seconds,
        )

    def clear(self) -> None:
        self._entries.clear()

