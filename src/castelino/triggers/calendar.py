"""Economic calendar — high-impact macro events.

US events are sourced from the FRED API (/releases/dates endpoint) with a
configurable TTL cache. Non-US events (ECB, BoJ, BoE, OPEC, etc.) are fetched
via the Perplexity Sonar API (search-grounded LLM) and cached locally; a static
fallback list is used when the API key is missing or the call fails.

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
from openai import OpenAI

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
# Non-US events via Perplexity Sonar API (with static fallback)
# ---------------------------------------------------------------------------

_STATIC_NON_US_EVENTS: list[dict] = [
    {"date": "2026-06-04", "name": "ECB Rate Decision", "region": "EU", "impact": "high",
     "asset_classes": ["fx", "bond_etf"]},
    {"date": "2026-07-02", "name": "OPEC+ Meeting", "region": "GLOBAL", "impact": "high",
     "asset_classes": ["commodity_etf", "futures"]},
    {"date": "2026-07-25", "name": "BoJ Rate Decision", "region": "JP", "impact": "high",
     "asset_classes": ["fx", "bond_etf"]},
]

_SONAR_PROMPT = """\
Return ONLY a JSON array of upcoming high-impact non-US macroeconomic events \
within the next {window_days} days (from {today}). Include central bank rate \
decisions, GDP/CPI releases, OPEC meetings, and major policy announcements \
for regions: {regions}.

Each element must have exactly these keys:
  "date": "YYYY-MM-DD",
  "name": "<event name>",
  "region": "<one of: EU, UK, JP, CN, GLOBAL>",
  "impact": "<high or medium>",
  "asset_classes": [<subset of: "equity", "bond_etf", "fx", "commodity_etf", "futures">]

Return ONLY the JSON array, no markdown fences, no commentary.\
"""


def _sonar_cache_path() -> Path:
    return get_settings().resolved_paths.cache / "sonar_non_us_calendar.json"


def _sonar_cache_is_fresh() -> bool:
    p = _sonar_cache_path()
    if not p.exists():
        return False
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
    ttl = timedelta(hours=get_settings().sonar.cache_ttl_hours)
    return (datetime.now(UTC) - mtime) < ttl


def _parse_sonar_response(raw_text: str) -> list[dict]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def _fetch_sonar_events(window_days: int) -> list[CalendarEvent]:
    cfg = get_settings()
    api_key = cfg.perplexity_api_key
    if not api_key:
        log.debug("PERPLEXITY_API_KEY not set — skipping Sonar calendar fetch")
        return []

    cache_path = _sonar_cache_path()
    if _sonar_cache_is_fresh():
        try:
            raw = json.loads(cache_path.read_text())
            return _dicts_to_events(raw, window_days)
        except (json.JSONDecodeError, KeyError):
            log.warning("sonar cache corrupt — refetching")

    sonar_cfg = cfg.sonar
    today = date.today()
    prompt = _SONAR_PROMPT.format(
        window_days=window_days,
        today=today.isoformat(),
        regions=", ".join(sonar_cfg.regions),
    )

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.perplexity.ai",
        )
        resp = client.chat.completions.create(
            model=sonar_cfg.model,
            messages=[
                {"role": "system", "content": "You are a macro-economic calendar data provider. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        content = resp.choices[0].message.content or ""
        parsed = _parse_sonar_response(content)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(parsed, indent=2))
        return _dicts_to_events(parsed, window_days)
    except Exception as e:
        log.warning("Sonar API call failed: %s — falling back to cache/static", e)
        if cache_path.exists():
            try:
                raw = json.loads(cache_path.read_text())
                return _dicts_to_events(raw, window_days)
            except (json.JSONDecodeError, KeyError):
                pass
        return []


def _dicts_to_events(raw: list[dict], window_days: int) -> list[CalendarEvent]:
    today = date.today()
    horizon = today + timedelta(days=window_days)
    events: list[CalendarEvent] = []
    for r in raw:
        try:
            d = date.fromisoformat(r["date"])
        except (KeyError, ValueError):
            continue
        if d < today or d > horizon:
            continue
        region = r.get("region", "GLOBAL")
        rt = time(12, 0, tzinfo=UTC)
        ts = datetime.combine(d, rt, tzinfo=UTC)
        events.append(
            CalendarEvent(
                timestamp=ts,
                name=r.get("name", "Unknown Event"),
                region=region,
                impact=r.get("impact", "medium"),
                asset_classes_affected=r.get("asset_classes", ["fx"]),
            )
        )
    return events


def _load_static_non_us(window_days: int) -> list[CalendarEvent]:
    return _dicts_to_events(_STATIC_NON_US_EVENTS, window_days)


def _load_non_us_events(window_days: int = 30) -> list[CalendarEvent]:
    events = _fetch_sonar_events(window_days)
    if events:
        return events
    log.info("sonar returned no events — using static non-US fallback")
    return _load_static_non_us(window_days)


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
