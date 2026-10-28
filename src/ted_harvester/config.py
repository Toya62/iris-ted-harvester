"""Runtime configuration from environment variables only (no secrets in code)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    api_url: str = "https://api.ted.europa.eu/v3/notices/search"
    database_url: str | None = None
    countries: tuple[str, ...] = ("DEU",)
    page_limit: int = 100
    window_days: int = 30
    timeout_s: int = 30
    max_retries: int = 5
    overlap_days: int = 3
    default_lookback_days: int = 90
    nuts_centroids: str = "data/nuts3_centroids.csv"
    backoff_base_s: float = 1.0
    user_agent: str = "iris-ted-harvester/0.1"

    @classmethod
    def from_env(cls) -> "Settings":
        raw = os.environ.get("TED_COUNTRIES", "DEU").strip()
        countries = () if raw.upper() in ("", "ALL") else tuple(c.strip().upper() for c in raw.split(",") if c.strip())
        limit = _int("TED_PAGE_LIMIT", 100)
        if not 1 <= limit <= 250:
            raise ValueError("TED_PAGE_LIMIT must be between 1 and 250")
        return cls(
            api_url=os.environ.get("TED_API_URL", cls.api_url),
            database_url=os.environ.get("DATABASE_URL") or None,
            countries=countries, page_limit=limit,
            window_days=_int("TED_WINDOW_DAYS", 30), timeout_s=_int("TED_TIMEOUT_S", 30),
            max_retries=_int("TED_MAX_RETRIES", 5), overlap_days=_int("TED_OVERLAP_DAYS", 3),
            default_lookback_days=_int("TED_DEFAULT_LOOKBACK_DAYS", 90),
            nuts_centroids=os.environ.get("TED_NUTS_CENTROIDS", cls.nuts_centroids),
        )
