"""Page 1's week-in-markets table and ARC regime read: code only, no LLM."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from castelino.agents.weekly.models import RegimeRead, ScoreRow

log = logging.getLogger(__name__)

# (asset, provider, symbol, unit)
ROWS = [
    ("S&P 500", "yahoo", "^GSPC", "level"),
    ("Nasdaq 100", "yahoo", "^NDX", "level"),
    ("Philadelphia Semis (SOX)", "yahoo", "^SOX", "level"),
    ("US 10y yield", "fred", "DGS10", "%"),
    ("US 2y yield", "fred", "DGS2", "%"),
    ("Dollar index (DXY)", "yahoo", "DX-Y.NYB", "level"),
    ("Brent crude", "yahoo", "BZ=F", "$"),
]


def _at(s: pd.Series, d: date) -> float | None:
    sub = s[s.index <= pd.Timestamp(d)]
    return float(sub.iloc[-1]) if len(sub) else None


def score_row(asset: str, unit: str, s: pd.Series, end: date) -> ScoreRow | None:
    s = s.dropna()
    s = s[s.index <= pd.Timestamp(end)]
    if s.empty:
        return None
    lvl = float(s.iloc[-1])
    bp = unit == "%"

    def chg(then: float | None) -> float | None:
        if then is None:
            return None
        return round((lvl - then) * 100) if bp else round((lvl / then - 1) * 100, 1)

    return ScoreRow(
        asset=asset,
        level=round(lvl, 2),
        unit=unit,
        change_unit="bp" if bp else "%",
        w1=chg(_at(s, end - timedelta(days=7))),
        m1=chg(_at(s, end - timedelta(days=30))),
        m3=chg(_at(s, end - timedelta(days=91))),
        ytd=chg(_at(s, date(end.year - 1, 12, 31))),
    )


def build_scorecard(end: date, *, fred=None, yahoo=None) -> list[ScoreRow]:
    from castelino.forecast import regime

    fred = fred or regime._fetch_fred_series
    yahoo = yahoo or regime._fetch_yf_close
    rows: list[ScoreRow] = []
    for asset, provider, symbol, unit in ROWS:
        try:
            row = score_row(asset, unit, (fred if provider == "fred" else yahoo)(symbol), end)
        except Exception as exc:  # noqa: BLE001 — one dead source drops one row
            log.warning("scorecard %s failed: %s", symbol, exc)
            continue
        if row:
            rows.append(row)
    return rows


def regime_read(current) -> RegimeRead:
    if current is None:
        return RegimeRead()
    return RegimeRead(
        pulse=round(current.growth.prob_up * 100), pressure=round(current.inflation.prob_up * 100)
    )
