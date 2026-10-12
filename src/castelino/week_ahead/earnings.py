"""Earnings dates for the S&P 500 plus a hand-kept list of non-US AI names.

The list is data/week_ahead/universe.csv (rebuild with scripts/build_week_ahead_universe.py).
"""

from __future__ import annotations

import csv
import logging
from datetime import date, timedelta
from pathlib import Path

from castelino.week_ahead import nasdaq
from castelino.week_ahead.econ import parse_num

log = logging.getLogger(__name__)
SESSION = {"time-pre-market": "pre", "time-after-hours": "post"}


def universe_path() -> Path:
    from castelino.config import get_settings

    return get_settings().root / "data" / "week_ahead" / "universe.csv"


def _norm(sym: str) -> str:
    return sym.strip().upper().replace("/", ".")  # Nasdaq writes BRK/B, the CSV BRK.B


def load_universe(path: Path) -> dict[str, tuple[str, str]]:
    with path.open() as f:
        return {_norm(r["ticker"]): (r["name"], r["group"]) for r in csv.DictReader(f)}


def _event(day: date, ticker: str, name: str, group: str, **kw) -> dict:
    return {
        "date": day.isoformat(),
        "time_et": None,
        "kind": "earnings",
        "name": name,
        "ticker": ticker,
        "company": name,
        "group": group,
        "market_cap": kw.get("market_cap"),
        "eps_est": kw.get("eps_est"),
        "eps_year_ago": kw.get("eps_year_ago"),
        "session": kw.get("session"),
    }


def from_nasdaq(rows: list[dict], day: date, universe: dict[str, tuple[str, str]]) -> list[dict]:
    out = []
    for r in rows:
        t = _norm(r.get("symbol") or "")
        if t not in universe:
            continue
        name, group = universe[t]
        out.append(
            _event(
                day,
                t,
                name,
                group,
                market_cap=parse_num(r.get("marketCap"))[0],
                eps_est=parse_num(r.get("epsForecast"))[0],
                eps_year_ago=parse_num(r.get("lastYearEPS"))[0],
                session=SESSION.get(r.get("time") or ""),
            )
        )
    return out


def yf_earnings(ticker: str) -> tuple[date | None, float | None]:
    """Next earnings date and EPS estimate from yfinance (for names without a US listing)."""
    import yfinance as yf

    cal = yf.Ticker(ticker).calendar or {}
    dates = cal.get("Earnings Date") or []
    return (dates[0] if dates else None), cal.get("Earnings Average")


def fetch_week(
    monday: date,
    universe: dict[str, tuple[str, str]],
    fetch=nasdaq.fetch_day,
    yf=yf_earnings,
) -> list[dict]:
    friday = monday + timedelta(days=4)
    out: list[dict] = []
    for i in range(5):
        d = monday + timedelta(days=i)
        out += from_nasdaq(fetch("earnings", d), d, universe)
    for t, (name, group) in universe.items():
        if group != "ai_extra" or "." not in t:
            continue
        try:
            d, eps = yf(t)
        except Exception as e:  # noqa: BLE001 - one missing name never fails the lane
            log.warning("yfinance earnings %s: %s", t, e)
            continue
        if d and monday <= d <= friday:
            out.append(_event(d, t, name, group, eps_est=eps))
    return out
