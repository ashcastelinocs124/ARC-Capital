"""Wave 4 — regression tests for materialize_order's gating + notional logic.

We test ~10 hand-crafted cases covering each branch. Property-based testing
was deferred because the deterministic logic is small and gating-heavy —
explicit cases catch regressions more legibly.
"""
from __future__ import annotations

import pytest

from castelino.agents.portfolio import materialize_order
from castelino.memory.schemas import Direction
from tests.backtest._builders import (
    make_decision,
    make_expression,
    make_guard,
    make_hypothesis,
    make_portfolio,
    patch_pricing_and_instrument,
)


@pytest.mark.backtest
def test_hold_action_returns_none(monkeypatch):
    patch_pricing_and_instrument(monkeypatch)
    out = materialize_order(
        decision=make_decision(action="hold"),
        expression=make_expression(),
        hypothesis=make_hypothesis(),
        guard=make_guard(),
        portfolio=make_portfolio(),
        gate_multiplier=1.0,
    )
    assert out is None


@pytest.mark.backtest
def test_hard_veto_returns_none(monkeypatch):
    patch_pricing_and_instrument(monkeypatch)
    out = materialize_order(
        decision=make_decision(action="open"),
        expression=make_expression(),
        hypothesis=make_hypothesis(),
        guard=make_guard(decision="hard_veto"),
        portfolio=make_portfolio(),
        gate_multiplier=1.0,
    )
    assert out is None


@pytest.mark.backtest
def test_zero_gate_multiplier_returns_none(monkeypatch):
    patch_pricing_and_instrument(monkeypatch)
    out = materialize_order(
        decision=make_decision(action="open"),
        expression=make_expression(),
        hypothesis=make_hypothesis(),
        guard=make_guard(),
        portfolio=make_portfolio(),
        gate_multiplier=0.0,
    )
    assert out is None


@pytest.mark.backtest
def test_open_long_produces_buy_order(monkeypatch):
    patch_pricing_and_instrument(monkeypatch, price=100.0)
    out = materialize_order(
        decision=make_decision(action="open", quantity_pct_nav=0.03),
        expression=make_expression(direction=Direction.LONG),
        hypothesis=make_hypothesis(),
        guard=make_guard(),
        portfolio=make_portfolio(cash=1_000_000),
        gate_multiplier=1.0,
    )
    assert out is not None
    assert out.side.value == "buy"
    # notional = 0.03 * 1_000_000 * 1.0 = 30_000 -> quantity = 30_000 / 100 = 300
    assert abs(out.quantity - 300.0) < 1e-6
    assert out.stop_loss == pytest.approx(95.0)  # 100 * (1 - 0.05)


@pytest.mark.backtest
def test_open_short_produces_sell_order(monkeypatch):
    patch_pricing_and_instrument(monkeypatch, price=100.0)
    out = materialize_order(
        decision=make_decision(action="open"),
        expression=make_expression(direction=Direction.SHORT),
        hypothesis=make_hypothesis(),
        guard=make_guard(),
        portfolio=make_portfolio(cash=1_000_000),
        gate_multiplier=1.0,
    )
    assert out is not None
    assert out.side.value == "sell"
    assert out.stop_loss == pytest.approx(105.0)  # 100 * (1 + 0.05) for short


@pytest.mark.backtest
def test_gate_multiplier_amplifies_notional(monkeypatch):
    """Capitulation tier gate multiplier intentionally pushes size above
    the input quantity_pct_nav cap — this is the contrarian-amplify design."""
    patch_pricing_and_instrument(monkeypatch, price=100.0)
    out = materialize_order(
        decision=make_decision(action="open", quantity_pct_nav=0.03),
        expression=make_expression(),
        hypothesis=make_hypothesis(),
        guard=make_guard(),
        portfolio=make_portfolio(cash=1_000_000),
        gate_multiplier=1.3,  # capitulation tier
    )
    assert out is not None
    # notional = 0.03 * 1_000_000 * 1.3 = 39_000 -> quantity = 390
    assert abs(out.quantity - 390.0) < 1e-6


@pytest.mark.backtest
def test_gate_multiplier_downsizes_notional(monkeypatch):
    """Caution tier gate multiplier (0.5) cuts the notional in half."""
    patch_pricing_and_instrument(monkeypatch, price=100.0)
    out = materialize_order(
        decision=make_decision(action="open", quantity_pct_nav=0.04),
        expression=make_expression(),
        hypothesis=make_hypothesis(),
        guard=make_guard(),
        portfolio=make_portfolio(cash=1_000_000),
        gate_multiplier=0.5,
    )
    assert out is not None
    # notional = 0.04 * 1_000_000 * 0.5 = 20_000 -> quantity = 200
    assert abs(out.quantity - 200.0) < 1e-6


@pytest.mark.backtest
def test_close_with_no_existing_position_returns_none(monkeypatch):
    patch_pricing_and_instrument(monkeypatch)
    out = materialize_order(
        decision=make_decision(action="close"),
        expression=make_expression(),
        hypothesis=make_hypothesis(),
        guard=make_guard(),
        portfolio=make_portfolio(),  # no positions
        gate_multiplier=1.0,
    )
    assert out is None


@pytest.mark.backtest
def test_amended_guard_does_not_block_order(monkeypatch):
    """`amended` guard decision is not the same as hard_veto — order
    should still be produced. (Whether amended_size_multiplier is honoured
    inside materialize_order is a separate question — currently it's NOT
    applied here; it's applied upstream in run_portfolio_agent.)"""
    patch_pricing_and_instrument(monkeypatch, price=100.0)
    out = materialize_order(
        decision=make_decision(action="open", quantity_pct_nav=0.03),
        expression=make_expression(),
        hypothesis=make_hypothesis(),
        guard=make_guard(decision="amended", amended_size_multiplier=0.7),
        portfolio=make_portfolio(cash=1_000_000),
        gate_multiplier=1.0,
    )
    assert out is not None
    # materialize_order doesn't apply amended_size_multiplier itself, so
    # quantity = 0.03 * 1_000_000 * 1.0 / 100 = 300
    assert abs(out.quantity - 300.0) < 1e-6


@pytest.mark.backtest
def test_nonpositive_nav_raises(monkeypatch):
    patch_pricing_and_instrument(monkeypatch)
    with pytest.raises(RuntimeError, match="NAV"):
        materialize_order(
            decision=make_decision(action="open"),
            expression=make_expression(),
            hypothesis=make_hypothesis(),
            guard=make_guard(),
            portfolio=make_portfolio(cash=0.0),
            gate_multiplier=1.0,
        )
