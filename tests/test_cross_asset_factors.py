from datetime import date

import numpy as np
import pandas as pd
import pytest

from castelino.cross_asset import factors as f


def _daily(start, end, values=None, freq="B"):
    idx = pd.date_range(start, end, freq=freq)
    vals = values if values is not None else np.arange(len(idx), dtype=float)
    return pd.Series(vals, index=idx, dtype=float)


def _down(_):
    raise RuntimeError("down")


def test_weekly_last_closes_holiday_week_on_thursday():
    # 2026-04-03 is Good Friday: the week's last trading day is Thursday 2026-04-02
    s = _daily("2026-03-30", "2026-04-10")
    s = s.drop(pd.Timestamp("2026-04-03"))
    w = f.weekly_last(s)
    assert pd.Timestamp("2026-04-03") in w.index  # week still labelled by its Friday
    assert w[pd.Timestamp("2026-04-03")] == s[pd.Timestamp("2026-04-02")]


def test_market_factor_units():
    idx = pd.date_range("2026-01-01", "2026-03-31", freq="B")
    fred = {
        "DGS2": pd.Series(np.linspace(4.0, 3.5, len(idx)), index=idx),  # % -> bp diff
        "DTWEXBGS": pd.Series(np.linspace(100, 110, len(idx)), index=idx),  # % change
    }

    def fetch_fred(sid):
        if sid not in fred:
            raise RuntimeError("down")
        return fred[sid]

    df, gaps = f.build_market_factors(
        date(2026, 3, 27), fetch_fred=fetch_fred, fetch_yf=_down, fetch_cftc=_down
    )
    last = df.index[-1]
    assert last == pd.Timestamp("2026-03-27")
    w2 = f.weekly_last(fred["DGS2"]).loc[:last]
    assert df.loc[last, "y2"] == pytest.approx((w2.iloc[-1] - w2.iloc[-2]) * 100)
    wd = f.weekly_last(fred["DTWEXBGS"]).loc[:last]
    assert df.loc[last, "usd"] == pytest.approx((wd.iloc[-1] / wd.iloc[-2] - 1) * 100)
    # every failed source is a gap and its column is all zeros, never missing
    assert any("VIX" in g for g in gaps) and any("positioning" in g.lower() for g in gaps)
    assert (df["vix"] == 0).all()
    assert not df.isna().any().any()


def test_latest_week_missing_for_slow_series_is_zero_and_a_gap():
    walcl = _daily("2026-01-07", "2026-03-18", freq="W-WED")  # last print a week early
    df, gaps = f.build_market_factors(
        date(2026, 3, 27),
        fetch_fred=lambda sid: walcl if sid == "WALCL" else _daily("2026-01-01", "2026-03-27"),
        fetch_yf=lambda sym: _daily("2026-01-01", "2026-03-27"),
        fetch_cftc=lambda code: _daily("2026-01-06", "2026-03-24", freq="W-TUE"),
    )
    assert df.loc[pd.Timestamp("2026-03-27"), "walcl"] == 0
    assert any("Fed balance sheet" in g and "2026-03-27" in g for g in gaps)


def test_asset_returns_are_weekly_log_pct():
    n = len(pd.date_range("2026-01-01", "2026-03-27", freq="B"))
    px = _daily("2026-01-01", "2026-03-27", np.linspace(100, 120, n))
    r = f.asset_returns(date(2026, 3, 27), fetch_yf=lambda sym: px)
    w = f.weekly_last(px)
    assert list(r.columns) == ["spx", "ief", "gld"]
    assert r.iloc[-1]["gld"] == pytest.approx(np.log(w.iloc[-1] / w.iloc[-2]) * 100)


def test_stale_asset_raises():
    stale = _daily("2026-01-01", "2026-03-20")  # a week behind week_end
    with pytest.raises(f.StaleAsset):
        f.asset_returns(date(2026, 3, 27), fetch_yf=lambda sym: stale)
