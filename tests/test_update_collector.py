import pandas as pd

from castelino.agents.update.collector import (
    bp, collect, long_label, pct, sector_trend, short_label,
)


def series(start, step, n=300):
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.Series([start + step * i for i in range(n)], index=idx, dtype=float)


def test_pct_and_bp():
    s = pd.Series([100.0, 101.0, 102.0, 110.0])
    assert pct(s, 1) == round((110 / 102 - 1) * 100, 2)
    assert bp(pd.Series([4.0, 4.08]), 1) == 8.0
    assert pct(s, 10) is None and bp(s, 10) is None


def test_labels():
    assert short_label(2.1, 6.8) == "accelerating"
    assert short_label(0.1, 6.8) == "up, fading"
    assert short_label(-0.9, -1.2) == "down, deepening"
    assert short_label(0.1, 0.2) == "flat"
    assert short_label(None, 1.0) == "n/a"
    assert long_label(5.5, 31.0) == "uptrend"
    assert long_label(-2.0, 31.0) == "uptrend, fading"
    assert long_label(3.0, -10.0) == "bottoming, turning up"
    assert long_label(1.0, 2.0) == "range-bound"


def test_sector_trend_relative_to_spy():
    strong = series(100, 1.0)
    spy = series(100, 0.2)
    t = sector_trend("XLE", strong, spy)
    assert t.sector == "XLE" and t.r1m > 0 and t.rel1m > 0 and t.rel12m > 0
    assert sector_trend("XLE", strong, None).rel1m is None


def fake_close(inst):
    if inst.instrument_id == "BROKEN":
        raise RuntimeError("boom")
    return series(100, 0.5)


def test_collect_builds_snapshot_with_fakes():
    monthly = lambda sid: pd.Series(  # noqa: E731
        [3.0 + 0.05 * i for i in range(30)],
        index=pd.date_range("2024-01-31", periods=30, freq="ME"))
    snap = collect(today="2026-09-30", prediction={}, model_note=None,
                   fetch_close=fake_close, fetch_monthly=monthly)
    assert snap.date == "2026-09-30"
    assert {"equities", "rates_credit", "commodities", "fx"} <= set(snap.asset_returns)
    assert any(s.sector == "XLE" for s in snap.sectors)
    assert snap.releases and snap.releases[0].latest is not None


def test_collect_survives_every_source_failing():
    def boom(*_a, **_k):
        raise RuntimeError("offline")
    snap = collect(today="2026-09-30", prediction={}, model_note=None,
                   fetch_close=boom, fetch_monthly=boom)
    assert snap.sectors == [] and snap.releases == []
    assert snap.data_gaps and all(isinstance(g, str) for g in snap.data_gaps)
