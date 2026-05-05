"""Economic calendar — high-impact macro events.

Free APIs for forward-looking econ calendars are flaky and rate-limited. For
v1 we ship a curated rolling window of the highest-impact recurring events
(FOMC, CPI/PCE, NFP, ECB, BoJ, OPEC). Refreshable via `scripts/refresh_calendar.py`
when the user wants to extend the horizon.

`pull_calendar()` returns the next 30 days of high-impact events. Surprise
magnitude (actual vs consensus) is folded in only AFTER the release lands.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from castelino.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalendarEvent:
    timestamp: datetime
    name: str
    region: str            # US, EU, JP, UK, GLOBAL
    impact: str            # high | medium | low
    asset_classes_affected: list[str]


# A curated rolling window — refreshed by `scripts/refresh_calendar.py` when
# the user adds new dates. The cron fallback covers gaps.
_DEFAULT_EVENTS: list[dict] = [
    # 2026 — illustrative high-impact recurring events. Dates are placeholder
    # third-week-of-month patterns; the real refresh script overwrites this.
    {"date": "2026-05-13", "name": "US CPI YoY", "region": "US", "impact": "high",
     "asset_classes": ["equity", "bond_etf", "fx"]},
    {"date": "2026-05-15", "name": "US Retail Sales", "region": "US", "impact": "medium",
     "asset_classes": ["equity"]},
    {"date": "2026-06-04", "name": "ECB Rate Decision", "region": "EU", "impact": "high",
     "asset_classes": ["fx", "bond_etf"]},
    {"date": "2026-06-06", "name": "US Non-Farm Payrolls", "region": "US", "impact": "high",
     "asset_classes": ["equity", "bond_etf", "fx"]},
    {"date": "2026-06-11", "name": "US CPI YoY", "region": "US", "impact": "high",
     "asset_classes": ["equity", "bond_etf", "fx"]},
    {"date": "2026-06-18", "name": "FOMC Rate Decision", "region": "US", "impact": "high",
     "asset_classes": ["equity", "bond_etf", "fx", "commodity_etf"]},
    {"date": "2026-06-26", "name": "US PCE YoY", "region": "US", "impact": "high",
     "asset_classes": ["equity", "bond_etf"]},
    {"date": "2026-07-02", "name": "OPEC+ Meeting", "region": "GLOBAL", "impact": "high",
     "asset_classes": ["commodity_etf", "futures"]},
    {"date": "2026-07-04", "name": "US Non-Farm Payrolls", "region": "US", "impact": "high",
     "asset_classes": ["equity", "bond_etf", "fx"]},
    {"date": "2026-07-15", "name": "US CPI YoY", "region": "US", "impact": "high",
     "asset_classes": ["equity", "bond_etf", "fx"]},
    {"date": "2026-07-30", "name": "FOMC Rate Decision", "region": "US", "impact": "high",
     "asset_classes": ["equity", "bond_etf", "fx", "commodity_etf"]},
]


def _calendar_path() -> Path:
    return get_settings().resolved_paths.data / "calendar_cache.json"


def _bootstrap_calendar(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_DEFAULT_EVENTS, indent=2))


def pull_calendar(window_days: int = 30) -> list[CalendarEvent]:
    """Read the calendar cache and return events in the next `window_days`.

    Bootstraps the cache from `_DEFAULT_EVENTS` if the file is missing.
    """
    path = _calendar_path()
    if not path.exists():
        _bootstrap_calendar(path)
    raw = json.loads(path.read_text())
    today = date.today()
    horizon = today + timedelta(days=window_days)

    events: list[CalendarEvent] = []
    for r in raw:
        d = date.fromisoformat(r["date"])
        if d < today or d > horizon:
            continue
        # Default release time: 13:30 UTC (8:30 ET) for US releases, 12:00 UTC otherwise.
        rt = time(13, 30) if r["region"] == "US" else time(12, 0)
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
    return sorted(events, key=lambda e: e.timestamp)


def events_due(now: datetime | None = None, window_minutes: int = 60) -> list[CalendarEvent]:
    """Return events whose release time is within the next `window_minutes`.

    The runner polls every poll_minutes; window_minutes should be ≥ poll_minutes.
    """
    now = now or datetime.now(UTC)
    upcoming = pull_calendar(window_days=2)
    out = []
    for e in upcoming:
        delta = (e.timestamp - now).total_seconds()
        if -window_minutes * 60 <= delta <= window_minutes * 60:
            out.append(e)
    return out
