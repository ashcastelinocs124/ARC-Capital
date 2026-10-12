"""Economic releases for the five largest economies, tiered: inflation and jobs first."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from castelino.week_ahead import nasdaq

COUNTRIES = {"United States": "US", "China": "CN", "Germany": "DE", "Japan": "JP", "India": "IN"}
INFLATION = re.compile(r"\b(CPI|PPI|WPI|HICP|PCE)\b|inflation", re.I)
JOBS = re.compile(r"payroll|unemploy|jobless|employment change|\bADP\b", re.I)
LEVEL = re.compile(
    r"\bindex\b|n\.s\.a", re.I
)  # index levels / unadjusted series aren't the headline
DROP = re.compile(r"auction", re.I)
HHMM = re.compile(r"\d{2}:\d{2}")


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


def _label_pairs(evs: list[dict]) -> None:
    """Nasdaq sends m/m and y/y under one name, in no fixed order: the larger value is y/y.

    ponytail: breaks in deflation (m/m can exceed y/y); fix with a per-series prior lookup if it bites.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in evs:
        if e["kind"] == "inflation":
            groups[(e["country"], e["time_et"], e["name"])].append(e)

    def size(e: dict) -> float:
        v = e["consensus"] if e["consensus"] is not None else e["previous"]
        return abs(v) if v is not None else 0.0

    for g in groups.values():
        if len(g) == 2:
            lo, hi = sorted(g, key=size)
            lo["measure"], hi["measure"] = "m/m", "y/y"


def events_for_day(rows: list[dict], day: date) -> list[dict]:
    out = []
    for r in rows:
        cc = COUNTRIES.get(r.get("country") or "")
        name = (r.get("eventName") or "").strip()
        if not cc or not name or DROP.search(name):
            continue
        cons, cu = parse_num(r.get("consensus"))
        prev, pu = parse_num(r.get("previous"))
        act, au = parse_num(r.get("actual"))
        t = (r.get("gmt") or "").strip()  # labelled gmt, but the times are ET (US CPI at 08:30)
        if t.lower() == "all day" and cons is None and prev is None:
            continue  # holidays
        if cc == "DE":
            name = re.sub(r"^German(y)?\s+", "", name)
        out.append(
            {
                "date": day.isoformat(),
                "time_et": t if HHMM.fullmatch(t) else None,
                "kind": kind_of(name),
                "country": cc,
                "name": name,
                "measure": None,
                "consensus": cons,
                "previous": prev,
                "actual": act,
                "unit": cu or pu or au,
            }
        )
    _label_pairs(out)
    return out


def fetch_week(monday: date, fetch=nasdaq.fetch_day) -> list[dict]:
    out: list[dict] = []
    for i in range(5):
        d = monday + timedelta(days=i)
        out += events_for_day(fetch("economicevents", d), d)
    if not out:  # five economies never go a whole week without a release: Nasdaq changed its reply
        raise RuntimeError(f"nasdaq: no releases for the week of {monday}")
    return out
