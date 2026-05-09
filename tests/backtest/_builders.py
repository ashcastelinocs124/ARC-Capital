"""Hand-crafted object builders for materialize_order regression tests.

We return concrete, schema-conformant instances rather than random samples
because materialize_order's logic is gating + arithmetic — better tested
with explicit cases than with property generators.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from castelino.agents.portfolio import PortfolioDecision
from castelino.execution.portfolio import Portfolio
from castelino.memory.schemas import (
    Conviction,
    Direction,
    GuardDecision,
    Hypothesis,
    KillCriterion,
    Regime,
    TradeExpression,
)


def make_kill_criterion() -> KillCriterion:
    return KillCriterion(
        description="VIX above 35 sustained for 3 days",
        metric="VIX",
        threshold=35.0,
        direction="above",
    )


def make_hypothesis() -> Hypothesis:
    return Hypothesis(
        parent_trigger_id="trg-test",
        parent_world_state_id="ws-test",
        thesis="Test thesis",
        regime=Regime.RISK_OFF,
        horizon_days=30,
        conviction=Conviction.MEDIUM,
        kill_criteria=[make_kill_criterion()],
        rationale="Test rationale",
    )


def make_expression(
    direction: Direction = Direction.LONG, instrument: str = "SPY"
) -> TradeExpression:
    return TradeExpression(
        parent_hypothesis_id="hyp-test",
        instrument_id=instrument,
        direction=direction,
        rationale="Test expression rationale",
        expected_holding_days=10,
        target_size_pct_nav=0.03,
        initial_stop_pct=0.05,
    )


def make_portfolio(cash: float = 1_000_000.0) -> Portfolio:
    return Portfolio(cash=cash, initial_nav=cash)


def make_decision(
    *,
    action: str = "open",
    quantity_pct_nav: float = 0.03,
    stop_loss_pct: float = 0.05,
) -> PortfolioDecision:
    return PortfolioDecision(
        action=action,
        quantity_pct_nav=quantity_pct_nav,
        stop_loss_pct=stop_loss_pct,
        notes="test",
        cite_kill_criterion="VIX above 35 sustained for 3 days",
    )


def make_guard(
    *,
    decision: str = "approved",
    amended_size_multiplier: float = 1.0,
) -> GuardDecision:
    return GuardDecision(
        parent_verdict_id="vdc-test",
        decision=decision,
        amended_size_multiplier=amended_size_multiplier,
        rationale="test",
    )


def patch_pricing_and_instrument(
    monkeypatch, *, price: float = 100.0, contract_multiplier: float = 1.0
):
    """Mock the two external deps materialize_order touches.

    `materialize_order` does `from castelino.execution.pricing import latest`
    at module top, so the bound name lives at `castelino.agents.portfolio.latest`.
    `get_instrument` is imported lazily inside the function from
    `castelino.data.instruments`, so we patch the source module.
    """
    quote = MagicMock(price=price)
    inst = MagicMock(contract_multiplier=contract_multiplier)
    monkeypatch.setattr(
        "castelino.execution.pricing.latest",
        lambda instrument_id: quote,
    )
    monkeypatch.setattr(
        "castelino.agents.portfolio.latest",
        lambda instrument_id: quote,
    )
    monkeypatch.setattr(
        "castelino.data.instruments.get_instrument",
        lambda instrument_id: inst,
    )
