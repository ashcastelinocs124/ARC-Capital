"""Economic calendar — high-impact macro events.

US events are sourced from the FRED API (/releases/dates endpoint) with a
configurable TTL cache. Non-US events (ECB, BoJ, OPEC) remain a curated static
list until a reliable free API is available.

`pull_calendar()` returns the next N days of high-impact events, merging both
sources and sorting chronologically.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import requests

from castelino.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalendarEvent:
    timestamp: datetime
    name: str
    region: str            # US, EU, JP, UK, GLOBAL
    impact: str            # high | medium | low
    asset_classes_affected: list[str]


# ---------------------------------------------------------------------------
# FRED API integration (US macro releases)
# ---------------------------------------------------------------------------


def _fred_cache_path() -> Path:
    return get_settings().resolved_paths.cache / "fred_calendar.json"


def _fred_cache_is_fresh() -> bool:
    p = _fred_cache_path()
    if not p.exists():
        return False
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
    ttl = timedelta(hours=get_settings().fred.cache_ttl_hours)
    return (datetime.now(UTC) - mtime) < ttl


def _parse_fred_raw(raw: dict) -> list[CalendarEvent]:
    cfg = get_settings()
    configured = cfg.fred.releases
    today = date.today()
    horizon = today + timedelta(days=90)
    events: list[CalendarEvent] = []
    for entry in raw.get("release_dates", []):
        rid = entry.get("release_id")
        if rid not in configured:
            continue
        d = date.fromisoformat(entry["date"])
        if d < today or d > horizon:
            continue
        meta = configured[rid]
        rt = time(13, 30, tzinfo=UTC)
        ts = datetime.combine(d, rt, tzinfo=UTC)
        events.append(
            CalendarEvent(
                timestamp=ts,
                name=meta.name,
                region="US",
                impact=meta.impact,
                asset_classes_affected=list(meta.asset_classes),
            )
        )
    return events


def _fetch_fred_releases() -> list[CalendarEvent]:
    """Fetch upcoming US release dates from FRED API. Caches for TTL hours."""
    cfg = get_settings()
    cache_path = _fred_cache_path()

    if _fred_cache_is_fresh():
        raw = json.loads(cache_path.read_text())
        return _parse_fred_raw(raw)

    api_key = cfg.fred_api_key
    params = {
        "api_key": api_key,
        "file_type": "json",
        "include_release_dates_with_no_data": "true",
    }
    try:
        resp = requests.get(
            "https://api.stlouisfed.org/fred/releases/dates",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(raw, indent=2))
    except (requests.RequestException, ValueError) as e:
        log.warning("FRED API request failed: %s — using stale cache", e)
        if cache_path.exists():
            raw = json.loads(cache_path.read_text())
        else:
            log.error("FRED API down and no cache exists; returning empty US calendar")
            return []

    return _parse_fred_raw(raw)


# ---------------------------------------------------------------------------
# Non-US static events
# ---------------------------------------------------------------------------

_NON_US_EVENTS: list[dict] = [
    {"date": "2026-06-04", "name": "ECB Rate Decision", "region": "EU", "impact": "high",
     "asset_classes": ["fx", "bond_etf"]},
    {"date": "2026-07-02", "name": "OPEC+ Meeting", "region": "GLOBAL", "impact": "high",
     "asset_classes": ["commodity_etf", "futures"]},
    {"date": "2026-07-25", "name": "BoJ Rate Decision", "region": "JP", "impact": "high",
     "asset_classes": ["fx", "bond_etf"]},
]


def _load_non_us_events(window_days: int = 30) -> list[CalendarEvent]:
    today = date.today()
    horizon = today + timedelta(days=window_days)
    events: list[CalendarEvent] = []
    for r in _NON_US_EVENTS:
        d = date.fromisoformat(r["date"])
        if d < today or d > horizon:
            continue
        rt = time(12, 0, tzinfo=UTC)
        ts = datetime.combine(d, rt, tzinfo=UTC)
        events.append(
            CalendarEvent(
                timestamp=ts,
                name=r["name"],
                region=r["region"],
                impact=r["impact"],
                asset_classes_affected=list(r["asset_classes"]),
            )
        )
    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pull_calendar(window_days: int = 30) -> list[CalendarEvent]:
    """Merge FRED US events with static non-US events."""
    us_events = _fetch_fred_releases()
    today = date.today()
    horizon = today + timedelta(days=window_days)
    us_events = [e for e in us_events if today <= e.timestamp.date() <= horizon]
    non_us = _load_non_us_events(window_days)
    return sorted(us_events + non_us, key=lambda e: e.timestamp)


def events_due(now: datetime | None = None, window_minutes: int = 60) -> list[CalendarEvent]:
    """Return events whose release time is within the next `window_minutes`.

    The runner polls every poll_minutes; window_minutes should be >= poll_minutes.
    """
    now = now or datetime.now(UTC)
    upcoming = pull_calendar(window_days=2)
    out = []
    for e in upcoming:
        delta = (e.timestamp - now).total_seconds()
        if -window_minutes * 60 <= delta <= window_minutes * 60:
            out.append(e)
    return out
