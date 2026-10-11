from datetime import date
from types import SimpleNamespace

import pandas as pd

from castelino.agents.weekly.scorecard import build_scorecard, regime_read, score_row

END = date(2026, 10, 9)


def daily(start_val, end_val):
    idx = pd.date_range("2025-12-01", "2026-10-12", freq="D")
    vals = [start_val + (end_val - start_val) * i / (len(idx) - 1) for i in range(len(idx))]
    return pd.Series(vals, index=idx)


def test_rate_row_in_bp_and_cut_at_week_end():
    s = daily(4.0, 5.0)
    row = score_row("US 10y yield", "%", s, END)
    assert row.change_unit == "bp" and row.level == round(float(s[:"2026-10-09"].iloc[-1]), 2)
    assert row.w1 > 0 and row.ytd > row.m3 > row.m1 > row.w1


def test_price_row_in_percent():
    row = score_row("S&P 500", "level", daily(100.0, 130.0), END)
    assert row.change_unit == "%" and row.ytd > 0


def test_failed_source_drops_the_row():
    def yahoo(t):
        if t == "^SOX":
            raise RuntimeError("down")
        return daily(100.0, 110.0)

    rows = build_scorecard(END, fred=lambda s: daily(4.0, 4.2), yahoo=yahoo)
    names = [r.asset for r in rows]
    assert "Philadelphia Semis (SOX)" not in names and "US 10y yield" in names and len(rows) == 6


def test_regime_read():
    cur = SimpleNamespace(
        growth=SimpleNamespace(prob_up=0.643), inflation=SimpleNamespace(prob_up=0.38)
    )
    r = regime_read(cur)
    assert (r.pulse, r.pressure) == (64, 38)
    assert regime_read(None).pulse is None
