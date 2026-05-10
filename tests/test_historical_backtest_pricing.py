"""Phase-1 tests: historical-backtest as-of pricing + env-var hook."""
from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from castelino.backtest import BACKTEST_AS_OF_ENV
from castelino.backtest import pricing as bt_pricing


@pytest.fixture
def fake_archive(monkeypatch, tmp_path):
    """Write a tiny historical-prices parquet and point the loader at it."""
    df = pd.DataFrame([
        {"instrument_id": "SPY", "date": pd.Timestamp("2024-01-02"), "close": 470.0},
        {"instrument_id": "SPY", "date": pd.Timestamp("2024-01-03"), "close": 472.5},
        {"instrument_id": "SPY", "date": pd.Timestamp("2024-01-04"), "close": 471.0},
        {"instrument_id": "AGG", "date": pd.Timestamp("2024-01-02"), "close": 96.5},
        {"instrument_id": "AGG", "date": pd.Timestamp("2024-01-04"), "close": 97.1},
    ])
    p = tmp_path / "historical_prices.parquet"
    df.to_parquet(p)
    monkeypatch.setattr(bt_pricing, "historical_prices_path", lambda: p)
    bt_pricing.clear_cache()
    yield p
    bt_pricing.clear_cache()


def test_latest_as_of_exact_match(fake_archive):
    out = bt_pricing.latest_as_of("SPY", date(2024, 1, 3))
    assert out.instrument_id == "SPY"
    assert out.price == pytest.approx(472.5)


def test_latest_as_of_picks_most_recent_on_or_before(fake_archive):
    """If `as_of` is a non-trading day, return the prior trading-day close."""
    out = bt_pricing.latest_as_of("AGG", date(2024, 1, 3))  # 1/3 missing for AGG
    assert out.price == pytest.approx(96.5)
    assert out.asof.date() == date(2024, 1, 2)


def test_latest_as_of_unknown_instrument(fake_archive):
    with pytest.raises(bt_pricing.HistoricalPricingError, match="No historical rows"):
        bt_pricing.latest_as_of("NONEXISTENT", date(2024, 1, 3))


def test_latest_as_of_before_first_row(fake_archive):
    with pytest.raises(bt_pricing.HistoricalPricingError, match="on or before"):
        bt_pricing.latest_as_of("SPY", date(2023, 12, 1))


def test_current_as_of_unset(monkeypatch):
    monkeypatch.delenv(BACKTEST_AS_OF_ENV, raising=False)
    assert bt_pricing.current_as_of() is None


def test_current_as_of_set(monkeypatch):
    monkeypatch.setenv(BACKTEST_AS_OF_ENV, "2024-03-15")
    assert bt_pricing.current_as_of() == date(2024, 3, 15)


def test_current_as_of_invalid_raises(monkeypatch):
    monkeypatch.setenv(BACKTEST_AS_OF_ENV, "not-a-date")
    with pytest.raises(bt_pricing.HistoricalPricingError):
        bt_pricing.current_as_of()


def test_execution_pricing_routes_through_archive(fake_archive, monkeypatch):
    """End-to-end: execution.pricing.latest() must short-circuit to historical
    archive when BACKTEST_AS_OF is set, bypassing OpenBB / yfinance entirely."""
    from castelino.execution import pricing as exec_pricing

    # Make any live path explode so a missed env-var-hook fails loudly.
    monkeypatch.setattr(
        exec_pricing, "_try_openbb",
        lambda iid: (_ for _ in ()).throw(AssertionError("OpenBB not bypassed")),
    )
    monkeypatch.setattr(
        exec_pricing, "history",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("history not bypassed")),
    )

    monkeypatch.setenv(BACKTEST_AS_OF_ENV, "2024-01-03")
    p = exec_pricing.latest("SPY")
    assert p.instrument_id == "SPY"
    assert p.price == pytest.approx(472.5)
