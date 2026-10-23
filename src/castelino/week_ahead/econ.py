"""Economic releases for the five largest economies, tiered: inflation and jobs first.

The source is Trading Economics (te.py; user rule 2026-10-22). Nasdaq's economic calendar filed its
releases a day late and left actuals blank for hours, so it is no longer read; Nasdaq stays only for
the earnings calendar."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

log = logging.getLogger(__name__)

INFLATION = re.compile(r"\b(CPI|PPI|WPI|HICP|PCE)\b|inflation", re.I)
JOBS = re.compile(r"payroll|unemploy|jobless|employment change|\bADP\b", re.I)
LEVEL = re.compile(
    r"\bindex\b|n\.s\.a", re.I
)  # index levels / unadjusted series aren't the headline
DROP = re.compile(r"auction", re.I)


def parse_num(s: str | None) -> tuple[float | None, str]:
    """'5.40%' -> (5.4, '%'); '($0.09)' -> (-0.09, ''); blank / N/A -> (None, '')."""
    s = (s or "").replace("&nbsp;", "").replace("$", "").strip()
    if not s:
        return None, ""
    unit = ""
    if s[-1] in "%KMBT":
        unit, s = s[-1], s[:-1]
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()").replace(",", ""))
    except ValueError:
        return None, ""
    return (-v if neg else v), unit


def kind_of(name: str) -> str:
    if INFLATION.search(name) and not LEVEL.search(name):
        return "inflation"
    if JOBS.search(name):
        return "jobs"
    return "other"


def fetch_week(monday: date, prior=(), get=None) -> list[dict]:
    """The week's releases (Monday to Friday, New York time) from each country's Trading Economics page.

    A page starts a day or two back, so a Thursday refresh can't re-read Monday: earlier days of the
    week keep `prior`'s rows (the last file of the same week), and so does a country whose page failed.
    """
    from castelino.week_ahead import te

    lo, hi = monday.isoformat(), (monday + timedelta(days=4)).isoformat()
    out: list[dict] = []
    read = 0
    for cc in te.SLUGS:
        try:
            evs = te.country_events(cc, get or te.get_page)
            if not evs:  # the page loaded but no row parsed: its layout changed
                raise RuntimeError("no rows parsed")
        except Exception as e:  # noqa: BLE001 - one country's page never blanks the others
            log.warning("week_ahead econ %s: %s", cc, str(e)[:120])
            out += [p for p in prior if p["country"] == cc]
            continue
        read += 1
        start = min((e["date"] for e in evs), default=hi)
        out += [e for e in evs if lo <= e["date"] <= hi]
        out += [p for p in prior if p["country"] == cc and p["date"] < start]
    if not read:
        raise RuntimeError(
            f"tradingeconomics: no releases for the week of {monday} (every page failed)"
        )
    return out
