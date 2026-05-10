"""Phase-5 tests: backtest portfolio bookkeeping + snapshot persistence +
mark-loop integration + NAV invariant + pipeline-fire wrapper."""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from castelino.backtest import execution as ex
from castelino.execution.portfolio import Portfolio


# ───────────────────────── snapshot persistence ──────────────────────────


@pytest.fixture
def runs_dir(monkeypatch, tmp_path):
    cfg = ex.get_settings()
    monkeypatch.setattr(cfg.backtest, "runs_dir", str(tmp_path / "runs"))
    return tmp_path / "runs"


def test_snapshot_row_pulls_derived_metrics():
    pf = Portfolio(cash=100000.0, initial_nav=100000.0)
    row = ex.snapshot_row(date(2024, 3, 15), pf)
    assert row.nav == 100000.0
    assert row.cash == 100000.0
    assert row.gross_exposure == 0.0
    assert row.net_exposure == 0.0
    assert row.n_positions == 0


def test_append_daily_snapshot_creates_and_appends(runs_dir):
    pf = Portfolio(cash=100000.0, initial_nav=100000.0)
    p1 = ex.append_daily_snapshot(
        "test-run", ex.snapshot_row(date(2024, 3, 11), pf),
    )
    assert p1.exists()

    pf.cash = 99950.0
    ex.append_daily_snapshot("test-run", ex.snapshot_row(date(2024, 3, 12), pf))

    df = ex.load_history("test-run")
    assert len(df) == 2
    assert list(df["date"]) == [pd.Timestamp("2024-03-11"), pd.Timestamp("2024-03-12")]
    assert df["cash"].iloc[1] == 99950.0


def test_append_daily_snapshot_upserts_same_date(runs_dir):
    pf = Portfolio(cash=100000.0, initial_nav=100000.0)
    ex.append_daily_snapshot("upsert-run", ex.snapshot_row(date(2024, 3, 11), pf))
    pf.cash = 99000.0
    ex.append_daily_snapshot("upsert-run", ex.snapshot_row(date(2024, 3, 11), pf))

    df = ex.load_history("upsert-run")
    assert len(df) == 1  # idempotent on date — second write replaces
    assert df["cash"].iloc[0] == 99000.0


def test_load_history_empty_when_no_run(runs_dir):
    df = ex.load_history("never-existed")
    assert df.empty
    assert "nav" in df.columns


# ───────────────────────── NAV invariant ─────────────────────────────────


def test_nav_invariant_holds_for_no_op():
    pf = Portfolio(cash=100000.0, initial_nav=100000.0)
    ex.assert_nav_invariant(
        pf, pf, slippage_total=0.0, commission_total=0.0,
    )


def test_nav_invariant_detects_phantom_credit():
    before = Portfolio(cash=100000.0, initial_nav=100000.0)
    after = Portfolio(cash=100100.0, initial_nav=100000.0)  # phantom +$100
    with pytest.raises(AssertionError, match="NAV invariant violated"):
        ex.assert_nav_invariant(
            before, after, slippage_total=0.0, commission_total=0.0,
        )


def test_nav_invariant_accounts_for_friction():
    before = Portfolio(cash=100000.0, initial_nav=100000.0)
    after = Portfolio(cash=99950.0, initial_nav=100000.0)  # 50 in friction
    ex.assert_nav_invariant(
        before, after, slippage_total=30.0, commission_total=20.0,
    )


# ───────────────────────── PortfolioHolder ───────────────────────────────


def test_portfolio_holder_threads_state():
    pf1 = Portfolio(cash=100000.0, initial_nav=100000.0)
    pf2 = Portfolio(cash=99000.0, initial_nav=100000.0)
    holder = ex.PortfolioHolder(pf1)
    assert holder.get() is pf1
    holder.set(pf2)
    assert holder.get() is pf2


def test_initial_portfolio_uses_backtest_initial_nav(monkeypatch):
    cfg = ex.get_settings()
    monkeypatch.setattr(cfg.backtest, "initial_nav", 250_000.0)
    pf = ex.initial_portfolio()
    assert pf.cash == 250_000.0
    assert pf.initial_nav == 250_000.0


# ───────────────────────── pipeline-fire callable ────────────────────────


def test_make_fire_fn_invokes_graph_and_threads_portfolio(runs_dir):
    """The fire callable must build a FundState, invoke the graph, and
    if the graph returns a new Portfolio, persist it back into the holder."""
    pf_initial = Portfolio(cash=100000.0, initial_nav=100000.0)
    pf_after = Portfolio(cash=99500.0, initial_nav=100000.0)
    holder = ex.PortfolioHolder(pf_initial)

    captured = {}
    class FakeGraph:
        def invoke(self, state):
            captured["state"] = state
            return {"portfolio": pf_after}

    fire = ex.make_fire_fn(holder, graph_builder=lambda: FakeGraph())

    from castelino.backtest.runner import HeadlineScore, TriggerCandidate
    trigger = TriggerCandidate(
        date=date(2024, 3, 15), path="black_swan",
        headline="Bank panic", materiality=0.95,
    )
    scores = [HeadlineScore(headline="x", materiality=0.5, source="nyt")]
    ok = fire(date(2024, 3, 15), trigger, scores)

    assert ok is True
    assert holder.get() is pf_after
    assert captured["state"].trigger.headline == "Bank panic"
    assert captured["state"].trigger.significance == 0.95
    # bt path "black_swan" maps to TriggerSource.NEWS
    from castelino.memory.schemas import TriggerSource
    assert captured["state"].trigger.source == TriggerSource.NEWS


def test_make_fire_fn_returns_false_on_graph_exception(runs_dir):
    holder = ex.PortfolioHolder(Portfolio(cash=100000.0, initial_nav=100000.0))
    class Boom:
        def invoke(self, state): raise RuntimeError("graph blew up")
    fire = ex.make_fire_fn(holder, graph_builder=lambda: Boom())

    from castelino.backtest.runner import HeadlineScore, TriggerCandidate
    trigger = TriggerCandidate(
        date=date(2024, 3, 15), path="news",
        headline="x", materiality=0.8,
    )
    ok = fire(date(2024, 3, 15), trigger, [])
    assert ok is False
