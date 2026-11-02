"""Builds data/dashboards/sector_signals.json, the Sector Signal Significance dashboard's one file.

Per SPDR sector ETF: find every past event of every signal (signals.py), measure the forward return
after each at several horizons, and test it against a time-shift null (stats.py). Benjamini-Hochberg
corrects for running ~500 tests at once. Then:

- regimes: the same test split by VIX (calm / stressed) and by SPY's trend (above / below its 200-day),
  so a signal that only works in calm markets says so;
- out of sample: re-run the whole procedure on the first 70% of history only and check whether the
  edges it calls real keep their sign in the last 30% it never saw; noise should hold about half the time;
- live: signals that fired in the last few sessions, each with its sector's own track record.

Prices come from yfinance (auto-adjusted daily OHLCV). If the download fails the run raises and the
previous file stays.
"""

from __future__ import annotations

import json
import logging
import zlib
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from castelino.dashboards.sector_signals import signals as sig
from castelino.dashboards.sector_signals import stats as st
from castelino.signals.sector_sentiment import SECTOR_ETFS

log = logging.getLogger(__name__)

SECTORS: list[tuple[str, str]] = [(name, etf) for name, (etf, _k) in SECTOR_ETFS.items()]
BENCH = "SPY"
VIX = "^VIX"
MIN_ROWS = 300  # a sector needs ~15 months of prices before its 200-day signals mean anything
REGIMES = {"vix": ("calm", "stressed"), "trend": ("up", "down")}


class NothingToDo(Exception):  # noqa: N818 - an outcome, not an error
    pass


def _root() -> Path:
    from castelino.config import get_settings

    return get_settings().root


def out_path() -> Path:
    return _root() / "data" / "dashboards" / "sector_signals.json"


# ── data ───────────────────────────────────────────────────────────────────


def fetch(start: str) -> tuple[dict[str, pd.DataFrame], pd.Series]:
    """Daily OHLCV for the sector ETFs and SPY, and VIX closes, from yfinance in one download."""
    import yfinance as yf

    tickers = [etf for _n, etf in SECTORS] + [BENCH, VIX]
    raw = yf.download(tickers, start=start, interval="1d", auto_adjust=True, group_by="ticker",
                      progress=False, threads=True)  # fmt: skip
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned no prices")
    prices: dict[str, pd.DataFrame] = {}
    for t in tickers:
        if t not in raw.columns.get_level_values(0):
            continue
        df = raw[t].rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
        df = df.dropna(subset=["close"])
        df.index = pd.to_datetime(df.index).tz_localize(None)
        prices[t] = df
    if BENCH not in prices or VIX not in prices:
        raise RuntimeError("yfinance download is missing SPY or VIX")
    return prices, prices.pop(VIX)["close"]


# ── the build ──────────────────────────────────────────────────────────────


def _r(v: float | None, d: int = 6) -> float | None:
    return None if v is None or not np.isfinite(v) else round(float(v), d)


def _clean(d: dict) -> dict:
    return {k: (_r(v) if isinstance(v, float) else v) for k, v in d.items()}


def _regime_states(
    index: pd.DatetimeIndex, vix: pd.Series, spy: pd.Series, vix_stressed: float
) -> dict[str, np.ndarray]:
    """Regime key -> array of state labels, one per row of `index` (as-of that day's close)."""
    v = vix.reindex(index, method="ffill").to_numpy()
    s = spy.reindex(index, method="ffill")
    sma = s.rolling(200).mean().to_numpy()
    s = s.to_numpy()
    vix_state = np.where(np.isnan(v), "", np.where(v >= vix_stressed, "stressed", "calm"))
    trend_state = np.where(np.isnan(sma), "", np.where(s > sma, "up", "down"))
    return {"vix": vix_state, "trend": trend_state}


def _seed(*parts: str) -> int:
    return zlib.crc32("|".join(parts).encode())


def _sector(name: str, etf: str, df: pd.DataFrame, spy: pd.Series, vix: pd.Series, cfg) -> dict:
    """Everything for one sector: raw tests (q-values and verdicts come later, across all sectors)."""
    hs, hmax = list(cfg.horizons), max(cfg.horizons)
    close = df["close"].to_numpy(dtype=float)
    n_rows = len(close)
    n_valid = n_rows - hmax  # rows with every horizon's forward return
    split = int(n_valid * cfg.oos_split)
    is_valid = split - hmax  # in-sample rows whose forward window ends before the split
    margin = max(hmax, cfg.cooldown)

    ev = sig.events(df, spy, cfg.cooldown)
    fwd = st.forward_returns(close, hs)
    # p-values come from vol-scaled returns: signals bunch up in volatile spells, where any average is
    # noisier, and a shifted calendar lands mostly in calmer ones; scaling by the volatility known on the
    # day keeps that from passing for an edge. Means, edges and hit rates stay in plain returns.
    scaled = st.vol_scaled(close, fwd, cfg.vol_window)
    regimes = _regime_states(df.index, vix, spy, cfg.vix_stressed)
    rng = np.random.default_rng(_seed(etf))
    offsets = st.shift_offsets(n_valid, margin, cfg.bootstrap, rng)
    offsets_is = st.shift_offsets(is_valid, margin, cfg.bootstrap, rng)
    path_valid = n_rows - cfg.path_days
    path_offsets = st.shift_offsets(path_valid, margin, min(cfg.bootstrap, 400), rng)
    dates = df.index

    tests, paths, recent, live = [], {}, {}, []
    for s in sig.SIGNALS:
        idx_all = ev[s.id]
        idx = idx_all[idx_all < n_valid]
        key = f"{etf}|{s.id}"
        for h in hs:
            full = st.event_test(fwd[h], idx, n_valid, offsets)
            full |= st.significance(scaled[h], idx, n_valid, offsets)
            ins = {"n": 0, "p": None, "edge": None}
            if is_valid > 2 * margin:
                is_idx = idx[idx < is_valid]
                ins = st.event_test(fwd[h], is_idx, is_valid, offsets_is)
                ins |= st.significance(scaled[h], is_idx, is_valid, offsets_is)
            oos_idx = idx[idx >= split]
            oos_edge = (float(fwd[h][oos_idx].mean() - fwd[h][split:n_valid].mean())
                        if len(oos_idx) else None)  # fmt: skip
            reg = {}
            for rk, states in REGIMES.items():
                lab = regimes[rk][:n_valid]
                reg[rk] = {
                    state: _clean(st.iid_test(fwd[h], scaled[h], idx[lab[idx] == state],
                                              np.flatnonzero(lab == state), cfg.bootstrap_regime, rng))
                    for state in states
                }  # fmt: skip
            tests.append({
                "sector": name, "etf": etf, "signal": s.id, "h": h, **_clean(full),
                "is": {"n": ins["n"], "p": _r(ins.get("p")), "edge": _r(ins.get("edge"))},
                "oos": {"n": int(len(oos_idx)), "edge": _r(oos_edge)},
                "regimes": reg,
            })  # fmt: skip

        # average path after the event vs the shifted calendars' 5-95% band (the drilldown chart)
        pidx = idx_all[idx_all < path_valid]
        if len(pidx) and len(path_offsets):
            real = st.forward_paths(close, pidx, cfg.path_days).mean(axis=0)
            shifted = (pidx[None, :] + path_offsets[:, None]) % path_valid
            steps = np.arange(cfg.path_days + 1)
            null_paths = (close[shifted[..., None] + steps] / close[shifted][..., None] - 1).mean(
                axis=1
            )
            lo, mid, hi = np.percentile(null_paths, [5, 50, 95], axis=0)
            paths[key] = {
                "n": int(len(pidx)),
                "mean": [_r(v) for v in real],
                "null_lo": [_r(v) for v in lo],
                "null_mid": [_r(v) for v in mid],
                "null_hi": [_r(v) for v in hi],
            }

        recent[key] = [
            {"date": dates[i].date().isoformat(), "close": _r(close[i], 4),
             **{f"r{h}": (_r(fwd[h][i]) if i + h < n_rows else None) for h in hs}}
            for i in idx_all[-cfg.recent_events:][::-1]
        ]  # fmt: skip
        for i in idx_all[idx_all >= n_rows - cfg.live_lookback_days]:
            live.append({
                "sector": name, "etf": etf, "signal": s.id, "date": dates[i].date().isoformat(),
                "sessions_ago": int(n_rows - 1 - i), "close": _r(close[i], 4),
            })  # fmt: skip

    window = slice(max(0, n_rows - cfg.recent_days), n_rows)
    now_state = {rk: str(regimes[rk][-1]) for rk in REGIMES}
    chart = {
        "dates": [d.date().isoformat() for d in dates[window]],
        "close": [_r(c, 4) for c in close[window]],
        "events": {
            s.id: [dates[i].date().isoformat() for i in ev[s.id] if i >= window.start]
            for s in sig.SIGNALS
        },
    }
    info = {"sector": name, "etf": etf, "start": dates[0].date().isoformat(), "rows": n_rows,
            "oos_from": dates[split].date().isoformat(), "regime_now": now_state}  # fmt: skip
    return {
        "info": info,
        "tests": tests,
        "paths": paths,
        "recent": recent,
        "live": live,
        "chart": chart,
    }


def build(
    prices: dict[str, pd.DataFrame], vix: pd.Series, cfg, now: datetime | None = None
) -> dict:
    """The whole dashboard file from prices: pure, no network (tests feed it synthetic prices)."""
    now = now or datetime.now(UTC)
    spy = prices[BENCH]["close"]
    sectors, tests, paths, recent, live, charts, gaps = [], [], {}, {}, [], {}, []
    for name, etf in SECTORS:
        df = prices.get(etf)
        if df is None or len(df) < MIN_ROWS + max(cfg.horizons):
            gaps.append({"etf": etf, "reason": "not enough price history"})
            continue
        out = _sector(name, etf, df, spy, vix, cfg)
        sectors.append(out["info"])
        tests += out["tests"]
        paths |= out["paths"]
        recent |= out["recent"]
        live += out["live"]
        charts[etf] = out["chart"]
    if not sectors:
        raise NothingToDo("no sector had enough price history")

    # multiple-testing correction across every sector x signal x horizon with enough events
    def counted(t, n):
        return n >= cfg.min_events and t is not None

    full_p = [t["p"] if counted(t["p"], t["n"]) else None for t in tests]
    is_p = [t["is"]["p"] if counted(t["is"]["p"], t["is"]["n"]) else None for t in tests]
    for t, q, qi in zip(
        tests, st.benjamini_hochberg(full_p), st.benjamini_hochberg(is_p), strict=True
    ):
        t["q"] = _r(q)
        t["verdict"] = st.verdict(t["n"], t["p"], q, cfg.min_events, cfg.fdr, cfg.p_weak)
        exp = sig.BY_ID[t["signal"]].expected
        t["textbook"] = None if t["edge"] is None else bool(np.sign(t["edge"]) == exp)
        t["is"]["verdict"] = st.verdict(
            t["is"]["n"], t["is"]["p"], qi, cfg.min_events, cfg.fdr, cfg.p_weak
        )
        o = t["oos"]
        o["held"] = (None if o["edge"] is None or t["is"]["edge"] is None or o["n"] < cfg.min_oos_events
                     else bool(np.sign(o["edge"]) == np.sign(t["is"]["edge"])))  # fmt: skip

    # the honesty check: do in-sample "signals" keep their sign out of sample more often than noise?
    def hold_rate(verdicts: set[str]) -> dict:
        held = [
            t["oos"]["held"]
            for t in tests
            if t["is"]["verdict"] in verdicts and t["oos"]["held"] is not None
        ]
        return {"n": len(held), "rate": _r(sum(held) / len(held), 4) if held else None}

    oos = {
        "signal": hold_rate({"signal"}),
        "weak": hold_rate({"weak"}),
        "noise": hold_rate({"noise"}),
    }

    by_key = {(t["etf"], t["signal"], t["h"]): t for t in tests}
    for ev in live:
        rows = [by_key[(ev["etf"], ev["signal"], h)] for h in cfg.horizons]
        scored = [r for r in rows if r["verdict"] != "few"]
        best = (
            min(scored, key=lambda r: (r["q"] if r["q"] is not None else 1.0, -r["h"]))
            if scored
            else rows[-1]
        )
        ev["best_h"] = best["h"]
        ev["verdict"] = best["verdict"]

    rank = {"signal": 0, "weak": 1, "noise": 2, "few": 3}
    live.sort(key=lambda e: (rank[e["verdict"]], e["sessions_ago"], e["sector"]))
    counts = {
        h: {v: sum(1 for t in tests if t["h"] == h and t["verdict"] == v) for v in rank}
        for h in cfg.horizons
    }
    as_of = spy.index[-1].date().isoformat()
    vix_now = vix.dropna()
    return {
        "as_of": as_of,
        "generated_at": now.isoformat(),
        "source": "Yahoo Finance via yfinance: auto-adjusted daily prices of the SPDR sector ETFs, SPY and ^VIX",
        "params": {
            "horizons": list(cfg.horizons), "bootstrap": cfg.bootstrap, "fdr": cfg.fdr, "p_weak": cfg.p_weak,
            "min_events": cfg.min_events, "cooldown": cfg.cooldown, "vix_stressed": cfg.vix_stressed,
            "oos_split": cfg.oos_split, "vol_window": cfg.vol_window, "live_lookback_days": cfg.live_lookback_days, "path_days": cfg.path_days,
        },
        "regime_now": {
            "vix": _r(float(vix_now.iloc[-1]), 2) if len(vix_now) else None,
            "vix_state": sectors[0]["regime_now"]["vix"],
            "trend_state": sectors[0]["regime_now"]["trend"],
        },
        "catalog": [{"id": s.id, "label": s.label, "expected": s.expected, "family": s.family,
                     "description": s.description} for s in sig.SIGNALS],
        "sectors": sectors,
        "summary": {"tests": len(tests), "counts": {str(h): c for h, c in counts.items()}, "oos": oos},
        "live": live,
        "tests": tests,
        "paths": paths,
        "recent": recent,
        "charts": charts,
        "gaps": gaps,
    }  # fmt: skip


def run() -> str:
    from castelino.config import get_settings

    cfg = get_settings().sector_signals
    if not cfg.enabled:
        raise NothingToDo("disabled in config.yaml (sector_signals.enabled)")
    prices, vix = fetch(cfg.start)
    doc = build(prices, vix, cfg)
    p = out_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    tmp.replace(p)
    s = doc["summary"]["counts"][str(max(cfg.horizons))]
    return (f"{len(doc['sectors'])} sectors, {doc['summary']['tests']} tests "
            f"({s['signal']} signal at {max(cfg.horizons)}d); {len(doc['live'])} live")  # fmt: skip


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
