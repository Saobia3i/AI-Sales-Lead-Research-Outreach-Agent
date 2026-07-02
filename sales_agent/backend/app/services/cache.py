from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock

from app.config import settings
from app.schemas import CompanyProfile


class ResearchCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[datetime, CompanyProfile]] = {}
        self._lock = RLock()

    def get(self, key: str) -> CompanyProfile | None:
        normalized = self._normalize_key(key)
        with self._lock:
            item = self._items.get(normalized)
            if not item:
                return None
            cached_at, profile = item
            expires_at = cached_at + timedelta(seconds=settings.research_cache_ttl_seconds)
            if expires_at < datetime.now(timezone.utc):
                self._items.pop(normalized, None)
                return None
            return profile

    def set(self, key: str, profile: CompanyProfile) -> None:
        normalized = self._normalize_key(key)
        with self._lock:
            self._items[normalized] = (datetime.now(timezone.utc), profile)

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")


research_cache = ResearchCache()
