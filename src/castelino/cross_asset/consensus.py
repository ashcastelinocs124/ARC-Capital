"""Data-release surprises: first-reported actual vs consensus, found by cited web search.

A figure is accepted only if both numbers appear inside a cited part of the answer; the
answer's own JSON line doesn't count. Results are cached and never searched twice.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# key -> (label, group). payrolls in thousands; CPI/PCE m/m %, GDP q/q annualized %, ISM index
SERIES: dict[str, tuple[str, str]] = {
    "core_cpi": ("Core CPI m/m", "inflation"),
    "core_pce": ("Core PCE m/m", "inflation"),
    "payrolls": ("Nonfarm payrolls (k)", "growth"),
    "ism": ("ISM manufacturing PMI", "growth"),
    "gdp": ("Advance GDP q/q annualized", "growth"),
}
UNITS = {"core_cpi": "%", "core_pce": "%", "payrolls": "k", "ism": "", "gdp": "%"}
MAX_ATTEMPTS = 3
WINDOW_BEFORE = 300  # chars before a citation's end that it is taken to support

SYSTEM = (
    "You find US economic release figures. Use only reputable sources (BLS, BEA, ISM, Reuters, "
    "Bloomberg, WSJ, CNBC, MarketWatch, Trading Economics). Report the FIRST-REPORTED value, "
    "not revisions."
)
PROMPT = (
    "{label} for {period}: what was the first-reported actual value, the economists' consensus "
    "forecast just before the release, and the release date? Write one or two sentences stating "
    "both numbers with citations. Then, on the last line, output only JSON: "
    '{{"release_date": "YYYY-MM-DD", "actual": <number>, "consensus": <number>}}. '
    "{unit_note} If the release hasn't happened or you can't find a cited consensus, say so and "
    'output {{"release_date": null, "actual": null, "consensus": null}}.'
)
UNIT_NOTE = {
    "payrolls": "Give payrolls in thousands (e.g. 142 for +142,000).",
    "core_cpi": "Give the month-over-month % change (e.g. 0.3).",
    "core_pce": "Give the month-over-month % change (e.g. 0.3).",
    "gdp": "Give the annualized quarter-over-quarter % change of the ADVANCE estimate.",
    "ism": "Give the headline index level (e.g. 48.9).",
}
# (months after the reference period, day): earliest day a release can appear
EARLIEST = {
    "core_cpi": (1, 10),
    "core_pce": (1, 24),
    "payrolls": (1, 1),
    "ism": (1, 1),
    "gdp": (1, 24),
}


def _default_search(system: str, user: str):
    from castelino.data.web_search import search_cited

    return search_cited(system, user)


def periods(series: str, start: date, end: date) -> list[str]:
    if series == "gdp":
        qs = pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="Q")
        return [f"{q.year}-Q{q.quarter}" for q in qs]
    ms = pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M")
    return [f"{m.year}-{m.month:02d}" for m in ms]


def _month_after(period: str, n: int, day: int) -> date:
    if "Q" in period:
        y, q = period.split("-Q")
        last_month = pd.Period(f"{y}-{int(q) * 3:02d}", freq="M")
    else:
        last_month = pd.Period(period, freq="M")
    m = last_month + n
    return date(m.year, m.month, day)


def earliest_release(series: str, period: str) -> date:
    n, d = EARLIEST[series]
    return _month_after(period, n, d)


def surely_out(series: str, period: str) -> date:
    return _month_after(period, 2, 1)


def load_cache(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, indent=1, sort_keys=True))
    os.replace(tmp, path)


NEG_WORDS = re.compile(
    r"(fell|fall|declin\w*|decreas\w*|contract\w*|dropp?\w*|shr[ai]nk\w*|negative|minus|lost|loss)"
    r"\W+(?:\w+\W+){0,3}$",
    re.IGNORECASE,
)


def _variants(magnitude: float) -> set[str]:
    """Common written forms of a non-negative number (no sign)."""
    v = abs(magnitude)
    out = {f"{v:g}", f"{v:.1f}", f"{v:.2f}"}
    if float(v).is_integer():
        iv = int(v)
        out |= {f"{iv:,}", f"{iv * 1000:,}", f"{iv}k", f"{iv}K", str(iv * 1000)}
    return {s for s in out if s not in {"0", "0.0", "0.00"}} or {f"{v:g}"}


def number_cited(text: str, cites: list, value: float) -> bool:
    """True if `value` (in a common written form, with the right sign) appears in a span some
    citation supports. A negative needs a minus sign or a falling word just before the number;
    a positive must not carry a minus sign."""
    for _title, _url, start, end in cites:
        seg = text[max(0, start - WINDOW_BEFORE) : end + 1]
        for v in _variants(value):
            for m in re.finditer(rf"(?<![\d.]){re.escape(v)}(?![\d])", seg):
                before = seg[: m.start()]
                signed = before.rstrip(" ").endswith(("-", "−"))
                if value < 0 and (signed or NEG_WORDS.search(before)):
                    return True
                if value >= 0 and not signed:
                    return True
    return False


def lookup(series: str, period: str, search=_default_search) -> dict | None:
    label, _ = SERIES[series]
    user = PROMPT.format(label=label, period=period, unit_note=UNIT_NOTE[series])
    text, cites = search(SYSTEM, user)
    m = re.search(r"\{[^{}]*\"release_date\"[^{}]*\}\s*$", text.strip())
    if not m:
        return None
    try:
        rec = json.loads(m.group(0))
        actual, cons = float(rec["actual"]), float(rec["consensus"])
        released = date.fromisoformat(rec["release_date"]).isoformat()
    except (TypeError, ValueError, KeyError):
        return None
    prose = text.strip()[: m.start()]
    cited = [c for c in cites if c[2] < len(prose)]
    if not (number_cited(prose, cited, actual) and number_cited(prose, cited, cons)):
        return None
    return {"release_date": released, "actual": actual, "consensus": cons, "url": cited[0][1]}


def update(
    cache: dict,
    today: date,
    search=_default_search,
    cap: int | None = 10,
    start: date | None = None,
    seen: set[str] | None = None,
) -> int:
    """Search releases that are due and not final; returns how many searches were made.

    `seen` (optional) collects keys already searched by the caller's run and skips them, so a
    backfill loop never re-searches a release that is due but not out yet."""
    start = start or date(today.year - 2, today.month, 1)
    made = 0
    for series in SERIES:
        for period in periods(series, start, today):
            key = f"{series}:{period}"
            entry = cache.get(key, {"status": "pending", "attempts": 0})
            if entry["status"] in ("ok", "not_found") or today < earliest_release(series, period):
                continue
            if seen is not None and key in seen:
                continue
            if cap is not None and made >= cap:
                return made
            if seen is not None:
                seen.add(key)
            # an API error (down, out of credits) propagates: the release stays pending with no
            # attempt counted, and the caller stops instead of failing every remaining search
            rec = lookup(series, period, search)
            made += 1
            if rec:
                entry = {"status": "ok", "attempts": entry["attempts"] + 1, **rec}
            elif today >= surely_out(series, period):
                entry["attempts"] += 1
                if entry["attempts"] >= MAX_ATTEMPTS:
                    entry["status"] = "not_found"
            cache[key] = entry
    return made


def weekly_surprises(
    cache: dict, weeks: pd.DatetimeIndex
) -> tuple[pd.DataFrame, list[dict], list[str]]:
    """z = (actual - consensus) / std of that series' cached surprises, summed per week and group."""
    df = pd.DataFrame(0.0, index=weeks, columns=["inflation", "growth"])
    rows: list[dict] = []
    gaps: list[str] = []
    for series, (label, group) in SERIES.items():
        mine = sorted((k, v) for k, v in cache.items() if k.startswith(f"{series}:"))
        ok = [v for _, v in mine if v.get("status") == "ok"]
        surprises = np.array([v["actual"] - v["consensus"] for v in ok])
        sd = float(surprises.std()) if len(surprises) >= 4 else 0.0
        if ok and sd == 0:
            gaps.append(
                f"{label}: fewer than 4 cached releases or no variation, surprises set to 0"
            )
        for key, v in mine:
            period = key.split(":", 1)[1]
            if v.get("status") == "not_found":
                gaps.append(f"{label} ({period}): no cited consensus found, surprise set to 0")
            if v.get("status") != "ok" or sd == 0:
                continue
            z = (v["actual"] - v["consensus"]) / sd
            week = pd.Timestamp(v["release_date"]).to_period("W-FRI").end_time.normalize()
            if week in df.index:
                df.loc[week, group] += z
            rows.append(
                {
                    "series": series,
                    "label": f"{label.split(' (')[0]} ({period})",
                    "release_date": v["release_date"],
                    "actual": v["actual"],
                    "consensus": v["consensus"],
                    "z": round(float(z), 2),
                    "group": group,
                    "unit": UNITS[series],
                    "url": v["url"],
                }
            )
    rows.sort(key=lambda r: r["release_date"])
    return df, rows, gaps
