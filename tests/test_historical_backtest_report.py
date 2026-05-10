"""Phase-6 tests: backtest reporting — Sharpe / DD / monthlies / benchmarks."""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from castelino.backtest import execution as ex
from castelino.backtest import pricing as bt_pricing
from castelino.backtest import report as rp


# ───────────────────────── pure metric tests ─────────────────────────────


def test_sharpe_zero_when_no_volatility():
    flat = pd.Series([0.0001] * 100)
    # Std is 0 → return 0.0 by contract
    assert rp.sharpe(pd.Series([0.0] * 100)) == 0.0


def test_sharpe_positive_for_consistent_positive_returns():
    rng = np.random.default_rng(seed=42)
    rets = pd.Series(rng.normal(loc=0.001, scale=0.01, size=252))
    s = rp.sharpe(rets)
    # Should be roughly mean/std * sqrt(252) ≈ 1.6 — anywhere positive is fine
    assert s > 0.5


def test_max_drawdown_basic():
    nav = pd.Series([100, 110, 120, 90, 95, 130], index=pd.date_range("2024-01-01", periods=6))
    # Peak 120 → trough 90 → drawdown = -25%
    dd = rp.max_drawdown(nav)
    assert dd == pytest.approx(-0.25)


def test_max_drawdown_zero_when_monotonic_up():
    nav = pd.Series([100, 105, 110, 120, 130],
                    index=pd.date_range("2024-01-01", periods=5))
    assert rp.max_drawdown(nav) == 0.0


def test_annualized_return_one_year_flat():
    nav = pd.Series([100, 110],
                    index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2025-01-01")])
    ann = rp.annualized_return(nav)
    # 2024 is a leap year (366 days) → ann is slightly under 10%
    assert ann == pytest.approx(0.10, abs=5e-3)


def test_pct_months_positive_basic():
    # 6 months — 4 up, 2 down → 0.66...
    idx = pd.date_range("2024-01-31", periods=6, freq="ME")
    nav = pd.Series([100, 105, 102, 108, 107, 115], index=idx)
    assert rp.pct_months_positive(nav) == pytest.approx(3 / 5, abs=0.01)


# ──────────────── E2E build_report from a synthetic run ──────────────────


@pytest.fixture
def fake_run(monkeypatch, tmp_path):
    """Create a synthetic portfolio_history.parquet + tiny SPY archive."""
    cfg = ex.get_settings()
    monkeypatch.setattr(cfg.backtest, "runs_dir", str(tmp_path / "runs"))

    # 60 business days, NAV grows 10% with one drawdown
    bdays = pd.bdate_range("2024-01-02", periods=60)
    nav = np.linspace(1_000_000, 1_100_000, 60)
    nav[20:30] *= 0.93  # mid-run drawdown

    rows = pd.DataFrame({
        "date": bdays, "nav": nav,
        "cash": nav * 0.5,
        "gross_exposure": nav * 0.5,
        "net_exposure": nav * 0.3,
        "realized_pnl": nav - 1_000_000,
        "n_positions": [3] * 60,
    })
    p = ex.portfolio_history_path("rep-run")
    rows.to_parquet(p)

    # Tiny SPY + AGG archive aligned to the same dates
    bench = pd.DataFrame({
        "instrument_id": ["SPY"] * 60 + ["AGG"] * 60,
        "date": list(bdays) + list(bdays),
        "close": (
            list(np.linspace(470, 510, 60))
            + list(np.linspace(96, 99, 60))
        ),
    })
    archive_path = tmp_path / "historical_prices.parquet"
    bench.to_parquet(archive_path)
    monkeypatch.setattr(bt_pricing, "historical_prices_path", lambda: archive_path)
    bt_pricing.clear_cache()

    yield "rep-run", tmp_path
    bt_pricing.clear_cache()


def test_build_report_top_line_metrics(fake_run):
    run_id, _ = fake_run
    rep = rp.build_report(run_id)

    assert rep.run_id == run_id
    assert rep.top_line.n_business_days == 60
    # NAV starts at 1M, ends near 1.1M (with the dip)
    assert rep.top_line.start_nav == pytest.approx(1_000_000.0, rel=1e-6)
    assert rep.top_line.end_nav == pytest.approx(1_100_000.0, rel=1e-3)
    assert rep.top_line.total_return == pytest.approx(0.10, rel=1e-2)
    # Drawdown is ~7% from the *7%-cut* mid-run dip
    assert rep.top_line.max_drawdown < -0.05
    assert -1.0 <= rep.top_line.max_drawdown <= 0.0


def test_build_report_includes_benchmarks(fake_run):
    run_id, _ = fake_run
    rep = rp.build_report(run_id)
    names = sorted(b.name for b in rep.benchmarks)
    assert "SPY" in names
    assert "60/40 (SPY+AGG)" in names

    spy = next(b for b in rep.benchmarks if b.name == "SPY")
    # Synthetic NAV with a discrete jump produces a large-magnitude beta;
    # we just check the metric was computed (not NaN/Inf)
    assert np.isfinite(spy.beta)
    assert np.isfinite(spy.alpha_annualized)


def test_build_report_handles_missing_archive(monkeypatch, fake_run):
    run_id, tmp_path = fake_run
    # Point the archive somewhere that doesn't exist
    monkeypatch.setattr(bt_pricing, "historical_prices_path", lambda: tmp_path / "nope.parquet")
    bt_pricing.clear_cache()
    rep = rp.build_report(run_id)
    assert rep.benchmarks == []
    assert any("benchmark unavailable" in n for n in rep.notes)


def test_write_report_persists_json_and_html(fake_run):
    run_id, _ = fake_run
    json_path, html_path = rp.write_report(run_id)
    assert json_path.exists() and html_path.exists()

    payload = json.loads(json_path.read_text())
    assert payload["run_id"] == run_id
    assert "top_line" in payload
    assert "benchmarks" in payload

    html = html_path.read_text()
    assert run_id in html
    assert "Top-line" in html
    assert "Sharpe" in html
