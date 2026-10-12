"""Builds data/week_ahead.json.

Each lane runs on its own; a failed lane keeps this week's last good data (never another week's).
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from castelino.week_ahead import ai, earnings, econ, nasdaq, sectors, spend

log = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
CUTOVER = time(17, 0)  # from Friday's 17:00 publish, show next week
ECON_KINDS = {"inflation", "jobs", "other"}
QS = re.compile(r"\?\S*")


def out_path() -> Path:
    from castelino.config import get_settings

    return get_settings().root / "data" / "week_ahead.json"


def week_window(now: datetime) -> tuple[date, date]:
    local = now.astimezone(NY)
    d = local.date()
    wd = d.weekday()
    if wd >= 5 or (wd == 4 and local.time() >= CUTOVER):
        monday = d + timedelta(days=7 - wd)
    else:
        monday = d - timedelta(days=wd)
    return monday, monday + timedelta(days=4)


def _has_key() -> bool:
    from castelino.data.web_search import has_key

    return has_key()


def _default_search(system: str, user: str):
    from castelino.data.web_search import search_cited

    return search_cited(system, user)


def _write(out: Path, data: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, out)


def run(
    now: datetime | None = None,
    *,
    out: Path | None = None,
    universe: dict | None = None,
    fetch_day=nasdaq.fetch_day,
    yf=earnings.yf_earnings,
    get_json=ai.get_json,
    search=None,
    fetch_fred=spend.default_fred,
    get_text=spend.get_text,
    build_sectors=sectors.build,
) -> str:
    now = now or datetime.now(UTC)
    out = out or out_path()
    monday, friday = week_window(now)
    prev = json.loads(out.read_text()) if out.exists() else {}
    if prev.get("week_start") != monday.isoformat():
        prev = {}  # never carry another week's events
    prev_events = prev.get("events") or []
    prev_spend = prev.get("spend") or {}
    gaps: list[dict] = []
    failed = 0

    def lane(name, fn, fallback):
        nonlocal failed
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - one lane never blanks the page
            failed += 1
            msg = QS.sub("", str(e))[:200]
            log.warning("week_ahead %s failed: %s", name, msg)
            gaps.append({"lane": name, "error": msg})
            return fallback

    def kept(kinds: set[str]) -> list[dict]:
        return [e for e in prev_events if e["kind"] in kinds]

    def earnings_lane():
        u = universe or earnings.load_universe(earnings.universe_path())
        return earnings.fetch_week(monday, u, fetch_day, yf)

    def ai_lane():
        evs = ai.launched(monday, friday, get_json)
        if search is None and not _has_key():
            gaps.append({"lane": "ai", "error": "no OPENAI_API_KEY: reported launches skipped"})
            return evs
        try:  # a failed search (timeout, no credit) must not drop the confirmed launches
            return evs + ai.reported(monday, search or _default_search)
        except Exception as e:  # noqa: BLE001
            gaps.append({"lane": "ai", "error": "reported launches: " + QS.sub("", str(e))[:200]})
            return evs

    econ_ev = lane("econ", lambda: econ.fetch_week(monday, fetch_day), kept(ECON_KINDS))
    earn_ev = lane("earnings", earnings_lane, kept({"earnings"}))
    ai_ev = lane("ai", ai_lane, kept({"ai"}))
    ramp = lane("ramp", lambda: spend.ramp(fetch_fred), prev_spend.get("ramp") or {})
    orr = lane(
        "openrouter",
        lambda: spend.openrouter_share(get_text(spend.RANKINGS_URL)),
        prev_spend.get("openrouter"),
    )
    sec = lane(
        "sectors", lambda: build_sectors(now.astimezone(NY).date()), prev.get("sectors") or []
    )
    if failed == 6:
        raise RuntimeError("week_ahead: every lane failed; previous file kept")

    events = econ_ev + earn_ev + ai_ev
    _write(
        out,
        {
            "week_start": monday.isoformat(),
            "week_end": friday.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "events": events,
            "spend": {"ramp": ramp, "openrouter": orr},
            "sectors": sec,
            "gaps": gaps,
        },
    )
    return f"{len(events)} events for the week of {monday}; {len(gaps)} gaps"
