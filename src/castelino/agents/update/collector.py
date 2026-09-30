from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd

from castelino.agents.update.models import (
    MarketSnapshot,
    PredictionDelta,
    Release,
    SectorTrend,
)
from castelino.data.instruments import (
    AssetClass,
    Instrument,
    PriceSource,
    by_asset_class,
    get_instrument,
)

log = logging.getLogger(__name__)

SECTORS = ["XLE", "XLF", "XLI", "XLV", "XLK", "XLY"]
EQUITY_IDS = ["SPY", "QQQ", *SECTORS]
BARS = {"1d": 1, "1w": 5, "1m": 21, "3m": 63, "6m": 126, "12m": 252}
# (FRED id, display name, transform)
RELEASES = [
    ("CPIAUCSL", "CPI y/y", "yoy"),
    ("CPIAUCSL", "CPI m/m", "mom"),
    ("CPILFESL", "Core CPI y/y", "yoy"),
    ("CPILFESL", "Core CPI m/m", "mom"),
    ("PCEPI", "PCE y/y", "yoy"),
    ("PCEPI", "PCE m/m", "mom"),
    ("PCEPILFE", "Core PCE y/y", "yoy"),
    ("PCEPILFE", "Core PCE m/m", "mom"),
    ("UNRATE", "Unemployment rate", "level"),
    ("PAYEMS", "Payrolls y/y", "yoy"),
    ("INDPRO", "Industrial production y/y", "yoy"),
]


def pct(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) <= n:
        return None
    return round(float((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100), 2)


def bp(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) <= n:
        return None
    return round(float((s.iloc[-1] - s.iloc[-1 - n]) * 100), 2)


def short_label(r1w: float | None, r1m: float | None) -> str:
    if r1w is None or r1m is None:
        return "n/a"
    if r1m >= 1:
        return "accelerating" if r1w > r1m / 4 else "up, fading"
    if r1m <= -1:
        return "down, deepening" if r1w < r1m / 4 else "down, easing"
    return "flat"


def long_label(r3m: float | None, r12m: float | None) -> str:
    if r3m is None or r12m is None:
        return "n/a"
    if r12m >= 5:
        return "uptrend" if r3m > 0 else "uptrend, fading"
    if r12m <= -5:
        return "downtrend" if r3m < 0 else "bottoming, turning up"
    return "range-bound"


def _diff(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round(a - b, 2)


def sector_trend(sector: str, closes: pd.Series, spy: pd.Series | None) -> SectorTrend:
    r = {k: pct(closes, n) for k, n in BARS.items()}
    return SectorTrend(
        sector=sector,
        r1w=r["1w"],
        r1m=r["1m"],
        r3m=r["3m"],
        r6m=r["6m"],
        r12m=r["12m"],
        rel1m=_diff(r["1m"], pct(spy, BARS["1m"]) if spy is not None else None),
        rel12m=_diff(r["12m"], pct(spy, BARS["12m"]) if spy is not None else None),
        short_label=short_label(r["1w"], r["1m"]),
        long_label=long_label(r["3m"], r["12m"]),
    )


def asset_groups() -> dict[str, list[Instrument]]:
    return {
        "equities": [get_instrument(i) for i in EQUITY_IDS],
        "rates_credit": by_asset_class(AssetClass.BOND_ETF),
        "commodities": by_asset_class(AssetClass.COMMODITY_ETF)
        + by_asset_class(AssetClass.FUTURES),
        "fx": by_asset_class(AssetClass.FX),
    }


def default_fetch_close(inst: Instrument) -> pd.Series:
    from castelino.forecast import regime

    if inst.source == PriceSource.FRED:
        return regime._fetch_fred_series(inst.symbol)
    return regime._fetch_yf_close(inst.symbol)


def default_fetch_monthly(series_id: str) -> pd.Series:
    from castelino.forecast import regime

    return regime._fetch_fred_series(series_id)


def _release(series_id: str, name: str, kind: str, s: pd.Series) -> Release:
    s = s.dropna()
    if kind == "yoy":
        s = (s.pct_change(12) * 100).dropna()
    elif kind == "mom":
        s = (s.pct_change(1) * 100).dropna()
    if len(s) < 1:
        raise ValueError("no observations")
    latest = round(float(s.iloc[-1]), 2)
    prior = round(float(s.iloc[-2]), 2) if len(s) > 1 else None
    return Release(
        series=series_id, name=name, latest=latest, prior=prior, change=_diff(latest, prior)
    )


def _gap(label: str, exc: Exception) -> str:
    return f"{label} ({str(exc)[:80]})"


def collect(
    *,
    today: str,
    prediction: dict[str, PredictionDelta],
    model_note: str | None,
    fetch_close: Callable[[Instrument], pd.Series] = default_fetch_close,
    fetch_monthly: Callable[[str], pd.Series] = default_fetch_monthly,
) -> MarketSnapshot:
    gaps: list[str] = []
    closes: dict[str, pd.Series] = {}
    asset_returns: dict[str, dict[str, dict[str, float | None]]] = {}
    for cls, insts in asset_groups().items():
        rows: dict[str, dict[str, float | None]] = {}
        for inst in insts:
            try:
                s = fetch_close(inst).dropna()
            except Exception as exc:  # noqa: BLE001 — one bad source must not fail the run
                gaps.append(_gap(inst.instrument_id, exc))
                continue
            closes[inst.instrument_id] = s
            fn = bp if inst.source == PriceSource.FRED else pct  # yields move in bp
            rows[inst.instrument_id] = {k: fn(s, BARS[k]) for k in ("1d", "1w", "1m")}
        asset_returns[cls] = rows

    spy = closes.get("SPY")
    sectors = [sector_trend(x, closes[x], spy) for x in SECTORS if x in closes]

    releases: list[Release] = []
    fetched: dict[str, pd.Series | Exception] = {}
    for sid, name, kind in RELEASES:
        if sid not in fetched:
            try:
                fetched[sid] = fetch_monthly(sid)
            except Exception as exc:  # noqa: BLE001
                fetched[sid] = exc
        try:
            src = fetched[sid]
            if isinstance(src, Exception):
                raise src
            releases.append(_release(sid, name, kind, src))
        except Exception as exc:  # noqa: BLE001
            gap = _gap(sid, exc)
            if gap not in gaps:
                gaps.append(gap)

    return MarketSnapshot(
        date=today,
        releases=releases,
        asset_returns=asset_returns,
        sectors=sectors,
        prediction=prediction,
        data_gaps=gaps,
        model_note=model_note,
    )
