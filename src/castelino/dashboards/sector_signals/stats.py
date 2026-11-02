"""Event-study statistics: is a signal's average forward return different from chance?

The null is a *time shift*: slide the sector's whole event calendar by a random number of days
(wrapping around the end) and measure the forward return on the shifted dates. That keeps how many
events there were and how they cluster (a choppy year fires a lot), and breaks only their link to
what happened next. The p-value is how often a shifted calendar did as well as (or as badly as) the
real one, two-sided, around the shifted calendars' own mean.

Every return here is a simple return from the signal day's close to the close h trading days later,
so it's what you'd have had buying (or watching) at the close of the day the signal fired.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def forward_returns(close: np.ndarray, horizons: list[int]) -> dict[int, np.ndarray]:
    """h -> array as long as close: close[t+h] / close[t] - 1, NaN where t+h runs off the end."""
    out = {}
    for h in horizons:
        f = np.full(len(close), np.nan)
        if len(close) > h:
            f[:-h] = close[h:] / close[:-h] - 1
        out[h] = f
    return out


def vol_scaled(close: np.ndarray, fwd: dict[int, np.ndarray], window: int) -> dict[int, np.ndarray]:
    """Each forward return divided by the volatility known on the signal day: the standard deviation of
    the previous `window` daily log returns, scaled to h days (x sqrt(h)). Before a full window
    exists, the first full window's value stands in."""
    lr = np.diff(np.log(close), prepend=np.nan)
    sd = pd.Series(lr).rolling(window, min_periods=window).std().bfill().to_numpy()
    sd = np.where(sd > 0, sd, np.nan)
    # a flat stretch has no volatility to scale by; it counts as a zero move. The tail beyond the last
    # forward return stays NaN, as in fwd.
    return {
        h: np.where(np.isnan(f), np.nan, np.nan_to_num(f / (sd * math.sqrt(h))))
        for h, f in fwd.items()
    }


def forward_paths(close: np.ndarray, idx: np.ndarray, days: int) -> np.ndarray:
    """(len(idx), days+1) cumulative returns from each event's close: day 0 is 0."""
    if len(idx) == 0:
        return np.zeros((0, days + 1))
    steps = np.arange(days + 1)
    return close[idx[:, None] + steps[None, :]] / close[idx][:, None] - 1


def shift_offsets(n_valid: int, margin: int, b: int, rng: np.random.Generator) -> np.ndarray:
    """B random shifts in [margin, n_valid - margin): never so small that shifted windows mostly
    overlap the real ones."""
    lo, hi = margin, n_valid - margin
    if hi <= lo:
        return np.zeros(0, dtype=int)
    return rng.integers(lo, hi, size=b)


TAIL_MIN = 10  # fewer null draws this extreme -> the empirical p is too coarse; use the normal tail


def _p_two_sided(obs: float, null: np.ndarray) -> float:
    """Empirical two-sided p from the null draws. Past the last few draws it can't go below
    1/(B+1), which ~500 tests' false-discovery correction can never clear, so in the far tail the
    p-value comes from a normal fitted to the draws (a mean of many events is close to normal)."""
    m0 = float(null.mean())
    k = int((np.abs(null - m0) >= abs(obs - m0) - 1e-15).sum())
    if k >= TAIL_MIN or len(null) < 2:
        return float((1 + k) / (len(null) + 1))
    sd = float(null.std(ddof=1))
    if sd == 0:
        return float((1 + k) / (len(null) + 1))
    return float(math.erfc(abs(obs - m0) / sd / math.sqrt(2)))


def event_test(fwd: np.ndarray, idx: np.ndarray, n_valid: int, offsets: np.ndarray) -> dict:
    """One sector x signal x horizon. `idx` are event positions, all < n_valid (they have a forward
    return); `fwd` is the forward-return array whose first n_valid entries are finite."""
    base = fwd[:n_valid]
    out = {
        "n": int(len(idx)),
        "base_mean": float(np.mean(base)),
        "base_hit": float(np.mean(base > 0)),
    }
    if len(idx) == 0 or len(offsets) == 0:
        return out | {"mean": None, "hit": None, "null_mean": None, "null_sd": None,
                      "edge": None, "z": None, "p": None}  # fmt: skip
    r = fwd[idx]
    obs = float(r.mean())
    shifted = (idx[None, :] + offsets[:, None]) % n_valid  # (B, n)
    null = base[shifted].mean(axis=1)
    sd = float(null.std(ddof=1)) if len(null) > 1 else 0.0
    m0 = float(null.mean())
    return out | {
        "mean": obs,
        "hit": float(np.mean(r > 0)),
        "null_mean": m0,
        "null_sd": sd,
        "edge": obs - m0,
        "z": (obs - m0) / sd if sd > 0 else None,
        "p": _p_two_sided(obs, null),
    }


def significance(scaled: np.ndarray, idx: np.ndarray, n_valid: int, offsets: np.ndarray) -> dict:
    """p and z of the events against the time-shift null, on vol-scaled forward returns."""
    if len(idx) == 0 or len(offsets) == 0:
        return {"p": None, "z": None}
    out = event_test(scaled, idx, n_valid, offsets)
    return {"p": out["p"], "z": out["z"]}


def iid_test(
    fwd: np.ndarray,
    scaled: np.ndarray,
    idx: np.ndarray,
    pool: np.ndarray,
    b: int,
    rng: np.random.Generator,
) -> dict:
    """Events against random draws (with replacement) from `pool`, the days in the same regime.
    Used for the regime split, where a time shift would carry events into the other regime. Means
    and edge in plain returns; the p-value on vol-scaled ones, as in the main test."""
    if len(idx) == 0 or len(pool) == 0:
        return {
            "n": int(len(idx)),
            "mean": None,
            "base_mean": None,
            "edge": None,
            "hit": None,
            "p": None,
        }
    r, base = fwd[idx], fwd[pool]
    draws = scaled[pool][rng.integers(0, len(pool), size=(b, len(idx)))].mean(axis=1)
    obs, m0 = float(r.mean()), float(base.mean())
    return {
        "n": int(len(idx)),
        "mean": obs,
        "base_mean": m0,
        "edge": obs - m0,
        "hit": float(np.mean(r > 0)),
        "p": _p_two_sided(float(scaled[idx].mean()), draws),
    }


def benjamini_hochberg(p: list[float | None]) -> list[float | None]:
    """BH q-values (false discovery rate). None p-values stay None and don't count as tests."""
    have = [(i, v) for i, v in enumerate(p) if v is not None]
    q: list[float | None] = [None] * len(p)
    if not have:
        return q
    order = sorted(have, key=lambda t: t[1])
    m = len(order)
    running = 1.0
    for rank in range(m, 0, -1):
        i, v = order[rank - 1]
        running = min(running, v * m / rank)
        q[i] = min(running, 1.0)
    return q


def verdict(
    n: int, p: float | None, q: float | None, min_events: int, fdr: float, p_weak: float
) -> str:
    """signal: survives the false-discovery correction; weak: p-value alone says maybe; noise:
    indistinguishable from shifted calendars; few: too few events to tell."""
    if n < min_events or p is None:
        return "few"
    if q is not None and q <= fdr:
        return "signal"
    if p <= p_weak:
        return "weak"
    return "noise"
