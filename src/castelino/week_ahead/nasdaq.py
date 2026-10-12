"""Nasdaq's public calendar JSON (unofficial, keyless). Needs a browser User-Agent."""

from __future__ import annotations

from datetime import date

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
    r = httpx.get(
        URL.format(kind=kind), params={"date": day.isoformat()}, headers=HEADERS, timeout=30
    )
    if r.status_code != 200:
        raise RuntimeError(f"nasdaq {kind} {day}: HTTP {r.status_code}")
    data = (r.json() or {}).get("data") or {}
    return data.get("rows") or []
