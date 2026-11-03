"""The day's calendar for the Morning Note: the data releases and earnings Radar's week map shows for
the note's day, read fresh (data/week_ahead.json is rewritten in the same 17:00 refresh, so its
actuals can lag): economic releases from Trading Economics (user rule 2026-10-22), earnings from Nasdaq.

Two outputs. Every released result becomes a fact and a finding (releases as macro, earnings as news),
so the Editor can write an item about a big one and the guard can check its numbers. And every entry,
out or still to come, becomes a code-written line of "Other news on the calendar today" under the five items.
Data: US releases plus inflation and jobs abroad (the Theme Charts calendar's choice). Earnings: every
company in data/week_ahead/universe.csv on Nasdaq's day calendar, plus the hand-kept AI names Nasdaq
doesn't list (SpaceX) by Yahoo's earnings date. Nasdaq's day calendar carries no reported EPS, so the
result comes from Yahoo's earnings history, which lags a report by hours: a company without it yet is
listed as "reported before the open; EPS estimate $X", with no fact.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from castelino.agents.update.models import Fact, Finding
from castelino.week_ahead import nasdaq, te
from castelino.week_ahead.earnings import _norm, load_universe, universe_path
from castelino.week_ahead.econ import parse_num

PREFIX = "cal"  # fact ids cal1, cal2…; finding ids cal-1, cal-2…; rebuilt from scratch each call
ECON = ("Trading Economics calendar", "https://tradingeconomics.com/calendar")
EARN = ("Yahoo Finance earnings history", "https://finance.yahoo.com/calendar/earnings")
WHEN = {"pre": "reported before the open", "post": "reported after the close"}
QUARTER_DAYS = 75  # a report covers the quarter that ended at most this long before it


def _release(e: dict) -> tuple[str, list[float]]:
    from castelino.x_scout import fmt, label  # the X release posts' wording

    u = e.get("unit") or ""
    head = f"{e['time_et']} ET · {label(e)}" if e.get("time_et") else label(e)
    exp = f"{fmt(e['consensus'], u)} expected" if e["consensus"] is not None else ""
    prev = f"(previous {fmt(e['previous'], u)})" if e["previous"] is not None else ""
    if e["actual"] is None:
        return f"{head}: {' '.join(x for x in (exp, prev) if x) or 'due'}", []
    text = (
        f"{head}: {fmt(e['actual'], u)}"
        + (f" vs {exp}" if exp else "")
        + (f" {prev}" if prev else "")
    )
    return text, [v for v in (e["actual"], e["consensus"], e["previous"]) if v is not None]


def yahoo_eps(ticker: str, day: date) -> tuple[float, float | None, float | None] | None:
    """(EPS, estimate, surprise %) of the quarter reported on `day`: Yahoo's newest quarter, if it
    ended 1 to QUARTER_DAYS days before. None until Yahoo has it."""
    import yfinance as yf

    h = yf.Ticker(ticker).earnings_history
    if h is None or h.empty:
        return None
    h = h.sort_index()
    q, ended = h.iloc[-1], h.index[-1].date()
    ok = lambda v: v is not None and v == v  # noqa: E731 - NaN is not equal to itself
    if not (0 < (day - ended).days <= QUARTER_DAYS and ok(q["epsActual"])):
        return None
    est = round(float(q["epsEstimate"]), 2) if ok(q["epsEstimate"]) else None
    s = round(float(q["surprisePercent"]) * 100, 1) if ok(q["surprisePercent"]) else None
    return float(q["epsActual"]), est, s


def _earnings(
    name: str, ticker: str, session: str | None, est: float | None, got
) -> tuple[str, list[float]]:
    from castelino.x_scout import _money

    who = f"{name} ({ticker})"
    if not got:
        return f"{who} {WHEN.get(session or '', 'reports today')}" + (
            f"; EPS estimate {_money(est)}" if est is not None else ""
        ), []
    eps, est, s = got
    text = f"{who} EPS: {_money(eps)}" + (f" vs {_money(est)} expected" if est is not None else "")
    nums = [eps] + ([est] if est is not None else [])
    if est is not None and s is not None:
        pct = f"{abs(s):g}"
        art = "an" if re.match(r"8|1[18](\D|$)", pct) else "a"  # an 8%, an 11.4%, an 18%; a 110%
        text += f", {art} {pct}% {'beat' if s >= 0 else 'miss'}"
        nums.append(abs(s))
    return text, nums


def reporters(day: date, fetch, universe: dict, yf_date=None) -> list[dict]:
    """The universe's companies reporting on `day`: Nasdaq's day calendar, then the hand-kept AI
    names it lacks by Yahoo's date. Big AI names first, then by market value."""
    from castelino.week_ahead.earnings import SESSION, yf_earnings

    out = []
    for r in fetch("earnings", day):
        t = _norm(r.get("symbol") or "")
        if t in universe:
            mcap = parse_num(r.get("marketCap"))[0] or 0
            est = parse_num(r.get("epsForecast"))[0]
            out.append(
                {"ticker": t, "session": SESSION.get(r.get("time") or ""), "est": est, "mcap": mcap}
            )
    seen = {e["ticker"] for e in out}
    for t, (_, group) in universe.items():
        if group == "ai_extra" and t not in seen:
            try:
                d, est = (yf_date or yf_earnings)(t)
            except Exception:  # noqa: BLE001 - one missing name never fails the calendar
                continue
            if d == day:
                out.append({"ticker": t, "session": None, "est": est and round(est, 2), "mcap": 0})
    return sorted(out, key=lambda e: (universe[e["ticker"]][1] != "ai_extra", -e["mcap"]))


def lines(
    day: date,
    fetch=nasdaq.fetch_day,
    universe: dict | None = None,
    eps=yahoo_eps,
    yf_date=None,
    econ_day=None,
) -> list[tuple[str, list[float], str]]:
    """(text, numbers, kind) per calendar entry, releases by time then earnings; numbers is empty
    for an entry with no result yet. kind is "econ" or "earnings". `fetch` reads Nasdaq's earnings
    calendar; `econ_day` the day's economic releases (Trading Economics by default)."""
    econ = [
        e
        for e in (econ_day or te.day_events)(day)
        if e["country"] == "US" or e["kind"] in ("inflation", "jobs")
    ]
    out = [(*_release(e), "econ") for e in sorted(econ, key=lambda e: e.get("time_et") or "99:99")]
    universe = load_universe(universe_path()) if universe is None else universe
    reps = reporters(day, fetch, universe, yf_date)

    def got(t):
        try:
            return eps(t, day)
        except Exception:  # noqa: BLE001 - Yahoo throttling leaves the line without its result
            return None

    with ThreadPoolExecutor(8) as ex:  # one Yahoo call per company
        results = list(ex.map(got, [e["ticker"] for e in reps]))
    for e, g in zip(reps, results, strict=True):
        out.append(
            (
                *_earnings(universe[e["ticker"]][0], e["ticker"], e["session"], e["est"], g),
                "earnings",
            )
        )
    return out


def add(
    findings: list[Finding],
    facts: list[Fact],
    day: str,
    fetch=nasdaq.fetch_day,
    universe=None,
    **kw,
) -> tuple[list[Finding], list[Fact], list[str]]:
    """The day's findings and facts with this calendar's (re)added, and the section's lines."""
    findings = [f for f in findings if not f.id.startswith(f"{PREFIX}-")]
    facts = [f for f in facts if not (f.id.startswith(PREFIX) and f.id[len(PREFIX) :].isdigit())]
    out = lines(date.fromisoformat(day), fetch, universe, **kw)
    for text, nums, kind in out:
        if not nums:
            continue  # still to come: a line in the section, not a fact
        n = sum(f.id.startswith(f"{PREFIX}-") for f in findings) + 1
        title, url = ECON if kind == "econ" else EARN
        fact = Fact(
            id=f"{PREFIX}{n}",
            text=text,
            numbers=nums,
            provenance="data",
            source_title=title,
            source_url=url,
        )
        facts.append(fact)
        findings.append(
            Finding(
                id=f"{PREFIX}-{n}",
                agent="macro" if kind == "econ" else "news",
                claim=f"On today's calendar: {text}",
                provenance="data",
                source_title=title,
                source_url=url,
                fact_ids=[fact.id],
            )
        )
    return findings, facts, [text for text, _, _ in out]
