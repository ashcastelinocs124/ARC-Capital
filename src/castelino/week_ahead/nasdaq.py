"""Nasdaq's public calendar JSON (unofficial, keyless). Needs a browser User-Agent."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import httpx

URL = "https://api.nasdaq.com/api/calendar/{kind}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_day(kind: str, day: date) -> list[dict]:
    """kind = "earnings" | "economicevents". [] when Nasdaq has nothing for the day."""
    if kind == "economicevents":
        day += timedelta(days=econ_shift())
    return _rows(kind, day)


def _rows(kind: str, day: date) -> list[dict]:
    r = httpx.get(
        URL.format(kind=kind), params={"date": day.isoformat()}, headers=HEADERS, timeout=30
    )
    if r.status_code != 200:
        raise RuntimeError(f"nasdaq {kind} {day}: HTTP {r.status_code}")
    data = (r.json() or {}).get("data") or {}
    return data.get("rows") or []


def _today() -> date:
    return date.today()


@lru_cache(maxsize=1)
def econ_shift() -> int:
    """Days late Nasdaq files its economic calendar: in October 2026 economicevents?date=D answered with
    D-1's releases (Thursday's jobless claims came back for Friday's date), while the earnings calendar
    stayed right. Initial claims come out every Thursday, so the last two Thursdays show the shift; with
    no claims in reach, dates are read as given."""
    # ponytail: once per process (each cron run is one); a holiday week moves claims, hence two Thursdays
    today = _today()
    last = today - timedelta(days=(today.weekday() - 3) % 7 or 7)
    for thursday in (last, last - timedelta(days=7)):
        for shift in (0, 1):
            rows = _rows("economicevents", thursday + timedelta(days=shift))
            if any("Initial Jobless Claims" in (r.get("eventName") or "") for r in rows):
                return shift
    print("  nasdaq: no jobless claims on the last two Thursdays; reading economic dates as given")
    return 0
