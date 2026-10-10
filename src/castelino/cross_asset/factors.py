"""Weekly (Friday-close) factor moves and asset returns for the Cross-Asset Drivers model."""

from __future__ import annotations

from datetime import date

import httpx
import numpy as np
import pandas as pd

ASSETS: dict[str, tuple[str, str]] = {
    "spx": ("^GSPC", "S&P 500"),
    "ief": ("IEF", "Treasuries"),
    "gld": ("GLD", "Gold"),  # not GC=F: continuous-futures rolls would show up as Unexplained
}

# key -> (source, id, transform). bp = level diff x100 (series in %), diff = level diff, pct = % change
MARKET_FACTORS: dict[str, tuple[str, str, str]] = {
    "y2": ("fred", "DGS2", "bp"),
    "ry": ("fred", "DFII10", "bp"),
    "be": ("fred", "T10YIE", "bp"),
    "tp": ("fred", "THREEFYTP10", "bp"),
    "hy": ("fred", "BAMLH0A0HYM2", "bp"),
    "nfci": ("fred", "NFCI", "diff"),
    "walcl": ("fred", "WALCL", "pct"),
    "usd": ("fred", "DTWEXBGS", "pct"),
    "vix": ("yf", "^VIX", "diff"),
}

NAMES = {
    "y2": "2y yield",
    "ry": "Real yield",
    "be": "Breakeven",
    "tp": "Term premium",
    "hy": "HY spread",
    "nfci": "NFCI",
    "walcl": "Fed balance sheet",
    "usd": "Dollar",
    "vix": "VIX",
}

# CFTC Legacy futures-only report contract codes: E-mini S&P 500, 10-year T-note, gold (COMEX)
CFTC_CODES = {"spx": "13874A", "ief": "043602", "gld": "088691"}
# daily series must reach the week's last trading day; FRED posts Friday's values on Monday
DAILY = {"y2", "ry", "be", "tp", "hy", "usd", "vix"}
LATE = "not yet published"  # marks a latest-week gap; run.py recomputes such a week later
CFTC_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
HISTORY_START = "2018-01-01"


class StaleAsset(RuntimeError):  # noqa: N818 - matches refresh.Skipped's outcome naming
    """An asset's latest price is older than the week being explained."""


def _default_fred(series_id: str) -> pd.Series:
    from castelino.forecast.regime import _fetch_fred_series

    return _fetch_fred_series(series_id)


def _default_yf(symbol: str) -> pd.Series:
    from castelino.forecast.regime import _fetch_yf_close

    return _fetch_yf_close(symbol)


def fetch_cftc(code: str) -> pd.Series:
    """Net non-commercial position as % of open interest, indexed by report date (Tuesday)."""
    params = {
        "cftc_contract_market_code": code,
        "$where": f"report_date_as_yyyy_mm_dd >= '{HISTORY_START}'",
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": "5000",
    }
    rows = httpx.get(CFTC_URL, params=params, timeout=30).raise_for_status().json()
    if not rows:
        raise RuntimeError(f"CFTC returned no rows for {code}")
    df = pd.DataFrame(rows)
    net = df["noncomm_positions_long_all"].astype(float) - df["noncomm_positions_short_all"].astype(
        float
    )
    pct = net / df["open_interest_all"].astype(float) * 100
    return pd.Series(pct.values, index=pd.to_datetime(df["report_date_as_yyyy_mm_dd"]), name=code)


def weekly_last(s: pd.Series) -> pd.Series:
    """Last observation in each Friday-ending week, labelled by that Friday."""
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    return s.resample("W-FRI").last()


def _move(level: pd.Series, transform: str) -> pd.Series:
    if transform == "bp":
        return level.diff() * 100
    if transform == "pct":
        return level.pct_change() * 100
    return level.diff()


def _weeks(week_end: date) -> pd.DatetimeIndex:
    return pd.date_range(HISTORY_START, pd.Timestamp(week_end), freq="W-FRI")


def build_market_factors(
    week_end: date,
    fetch_fred=_default_fred,
    fetch_yf=_default_yf,
    fetch_cftc=fetch_cftc,
    asof: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Weekly moves for every market factor plus per-asset positioning. A failed source or an
    unpublished latest week becomes 0 (no information) and a data-gap message, never NaN.

    asof = the week's last trading day: a daily series that stops before it would otherwise
    measure a shorter week than the assets, so its latest week counts as unpublished."""
    idx = _weeks(week_end)
    out = pd.DataFrame(index=idx, dtype=float)
    gaps: list[str] = []
    wk = pd.Timestamp(week_end).date().isoformat()

    def add(key: str, name: str, level: pd.Series | None, transform: str) -> None:
        if level is None:
            out[key] = 0.0
            return
        level = level.dropna().loc[: pd.Timestamp(week_end)]
        w = weekly_last(level).reindex(idx)
        behind = key in DAILY and asof is not None and level.index.max() < asof
        missing_last = pd.isna(w.iloc[-1]) or behind
        if missing_last:
            gaps.append(f"{name}: {LATE} for week {wk}, move set to 0")
        move = _move(w.ffill(), transform)
        if missing_last:
            move.iloc[-1] = 0.0
        out[key] = move.fillna(0.0)

    for key, (src, sid, transform) in MARKET_FACTORS.items():
        try:
            level = fetch_fred(sid) if src == "fred" else fetch_yf(sid)
        except Exception as exc:  # noqa: BLE001 - one source failing must not stop the run
            gaps.append(f"{NAMES[key]} ({sid}): fetch failed ({exc}), excluded")
            level = None
        add(key, NAMES[key], level, transform)

    for asset, code in CFTC_CODES.items():
        name = f"Positioning {ASSETS[asset][1]}"
        try:
            level = fetch_cftc(code)
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"{name} (CFTC {code}): fetch failed ({exc}), excluded")
            level = None
        add(f"pos_{asset}", name, level, "diff")
    return out, gaps


def asset_returns(week_end: date, fetch_yf=_default_yf) -> pd.DataFrame:
    """Weekly log returns (%) per asset; `.attrs["last_bar"]` = the week's last trading day.

    Raises StaleAsset unless every asset has a close on that same day and it is Friday or
    Thursday (a Friday holiday). A missing Friday bar would publish a partial weekly return."""
    idx = _weeks(week_end)
    end = pd.Timestamp(week_end)
    prices = {k: fetch_yf(t).dropna().loc[:end] for k, (t, _) in ASSETS.items()}
    last = {k: px.index.max() for k, px in prices.items()}
    last_bar = max(last.values())
    for key, (ticker, name) in ASSETS.items():
        if last[key] < last_bar or last_bar < end - pd.Timedelta(days=1):
            raise StaleAsset(
                f"{name} ({ticker}) last close {last[key].date()} is short of week {week_end}"
            )
    cols = {}
    for key, px in prices.items():
        w = weekly_last(px).reindex(idx).ffill()
        cols[key] = np.log(w / w.shift(1)) * 100
    out = pd.DataFrame(cols, index=idx)
    out.attrs["last_bar"] = last_bar
    return out
