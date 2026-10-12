from datetime import date

import pandas as pd
import pytest

from castelino.week_ahead import sectors

ETFS = {"Energy": ("XLE", "energy"), "Technology": ("XLK", "technology")}


def closes(symbols, start):
    idx = pd.to_datetime(["2025-12-30", "2025-12-31", "2026-01-02", "2026-10-09"])
    data = {
        "XLE": [99, 100, 101, 150.5],
        "XLK": [199, 200, 210, 273.4],
        "SPY": [99, 100, 100, 114.9],
    }
    return pd.DataFrame({s: data[s] for s in symbols}, index=idx)


STOCKS = [
    {"sector": "Energy", "earnings_growth": -0.20},
    {"sector": "Energy", "earnings_growth": -0.14},
    {"sector": "Energy", "earnings_growth": 0.05},
    {"sector": "Technology", "earnings_growth": 1.17},
    {"sector": "Technology", "earnings_growth": None},
]


def build(**kw):
    kw.setdefault("closes", closes)
    kw.setdefault("pe", {"XLE": 18.8, "XLK": 32.1, "SPY": 24.7}.get)
    kw.setdefault("stocks", lambda: STOCKS)
    return sectors.build(date(2026, 10, 12), etfs=ETFS, **kw)


def test_ytd_from_last_close_of_last_year():
    rows = {r["etf"]: r for r in build()}
    assert rows["XLE"]["ytd"] == pytest.approx(50.5)
    assert rows["XLK"]["ytd"] == pytest.approx(36.7)
    assert rows["SPY"]["sector"] == "S&P 500" and rows["SPY"]["ytd"] == pytest.approx(14.9)


def test_pe_and_median_earnings_growth():
    rows = {r["etf"]: r for r in build()}
    assert rows["XLE"]["pe"] == 18.8 and rows["XLE"]["earnings_growth"] == pytest.approx(-14.0)
    assert rows["XLK"]["earnings_growth"] == pytest.approx(117.0)  # None skipped
    assert rows["SPY"]["earnings_growth"] is None


def test_missing_pe_or_snapshot_is_none_not_a_crash():
    rows = {r["etf"]: r for r in build(pe=lambda s: None, stocks=lambda: [])}
    assert rows["XLE"]["pe"] is None and rows["XLE"]["earnings_growth"] is None
    assert rows["XLE"]["ytd"] == pytest.approx(50.5)


def test_pe_lookup_error_is_none():
    def boom(s):
        raise RuntimeError("yahoo down")

    assert all(r["pe"] is None for r in build(pe=boom))


def test_no_prices_raises():
    def empty(symbols, start):
        return pd.DataFrame()

    with pytest.raises(RuntimeError, match="no sector prices"):
        build(closes=empty)
