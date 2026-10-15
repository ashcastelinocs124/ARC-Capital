"""Fear & Greed: zones, the sector scale, and compute() on a synthetic sell-off."""

import numpy as np
import pandas as pd

from castelino.signals import fear_greed as fg


def test_zone_edges():
    assert [fg.zone(s) for s in (0, 24.9, 25, 44.9, 45, 54.9, 55, 74.9, 75, 100)] == [
        "Extreme fear", "Extreme fear", "Fear", "Fear", "Neutral",
        "Neutral", "Greed", "Greed", "Extreme greed", "Extreme greed",
    ]  # fmt: skip


def test_sector_score_puts_the_label_lines_on_25_and_75():
    assert fg.sector_score(0.3) == 75
    assert fg.sector_score(-0.3) == 25
    assert fg.sector_score(0.0) == 50
    assert fg.sector_score(-0.9) == 0  # clipped


def _selloff():
    """3 years of a calm uptrend, then a 25-day crash: every signal should read fear."""
    days = pd.bdate_range(end="2026-10-14", periods=756)
    t = np.arange(len(days), dtype=float)
    crash = np.clip(t - (len(days) - 25), 0, None)  # 0 until the last 25 days, then 1, 2, ...
    wiggle = np.sin(t / 7)  # gives the trailing windows something to rank against
    spx = 4000 * (1 + 0.0004 * t) * (1 + 0.002 * wiggle) * (1 - 0.006 * crash)
    close = pd.DataFrame(
        {
            "^GSPC": spx,
            "^VIX": 15 + wiggle + 0.8 * crash,
            "IEF": 95 * (1 + 0.001 * wiggle) * (1 + 0.002 * crash),
            **{f"S{i}": spx * (1 + 0.01 * i) for i in range(5)},
        },
        index=days,
    )
    hy = pd.Series(3.0 + 0.05 * wiggle + 0.04 * crash, index=days)
    return close, hy


def test_compute_reads_a_selloff_as_extreme_fear():
    close, hy = _selloff()
    out = fg.compute(
        [f"S{i}" for i in range(5)], fetch_closes=lambda s: close, fetch_fred=lambda _: hy
    )
    assert out.as_of.isoformat() == "2026-10-14"
    assert out.zone == "Extreme fear" and out.score < 25
    assert {c.key: c.score < 25 for c in out.components} == dict.fromkeys(
        ["momentum", "breadth", "volatility", "junk", "haven"], True
    )
    assert out.previous is not None and out.week_ago is not None
    assert out.year_ago > 25  # a year ago the market was calm
    assert out.components[1].raw == "0% of our 5 stocks above their 200-day average"
