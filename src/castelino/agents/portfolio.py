"""Portfolio Agent — translate a (Verdict, GuardDecision) pair into a TradeOrder.

This is the LAST decision-making node before deterministic execution. The
Agent reads the book, reconciles with existing positions, and emits ONE
TradeOrder per accepted expression (or none if the guard vetoed).
"""

from __future__ import annotations

import logging
import uuid

from pydantic import BaseModel, Field

from castelino.agents.base import StructuredAgent
from castelino.execution.broker import OrderType, Side, TradeOrder
from castelino.execution.portfolio import Portfolio
from castelino.execution.pricing import PricingError, latest
from castelino.memory.schemas import (
    GuardDecision,
    Hypothesis,
    TradeExpression,
    Verdict,
)

log = logging.getLogger(__name__)


class PortfolioDecision(BaseModel):
    """Internal LLM output before we materialize a TradeOrder."""

    action: str = Field(pattern="^(open|close|trim|hold)$")
    quantity_pct_nav: float = Field(ge=0.0, le=0.05)
    stop_loss_pct: float = Field(ge=0.0, le=0.50)
    notes: str
    cite_kill_criterion: str = Field(min_length=3)


SYSTEM = """\
You are the Portfolio Agent. You translate an approved Verdict + GuardDecision
into ONE concrete book operation: open, close, trim, or hold.

Rules:
- If GuardDecision is 'hard_veto' → action must be 'hold'.
- If 'amended', use the amended_size_multiplier instead of expression.target_size.
- If the same instrument is already in the book in the SAME direction, prefer
  'hold' unless the verdict explicitly modifies. Reasoning: re-opening doubles
  exposure without adding signal.
- If the same instrument is already in the book in the OPPOSITE direction,
  emit 'close' first; the next pipeline cycle can reverse if appropriate.
- `cite_kill_criterion` is REQUIRED — copy at least one phrase from the
  hypothesis's kill_criteria. This enforces soft rule S4.
- `quantity_pct_nav` must be ≤ 5% (constitutional cap).
- `stop_loss_pct` is the % adverse move from entry that triggers a stop. Use
  the expression's initial_stop_pct unless the guard amended sizing — then
  scale proportionally.
"""


class PortfolioAgent(StructuredAgent[PortfolioDecision]):
    name = "portfolio"
    output_schema = PortfolioDecision
    tier = "reasoning"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self,
        *,
        verdict: Verdict,
        guard: GuardDecision,
        expression: TradeExpression,
        hypothesis: Hypothesis,
        portfolio: Portfolio,
    ) -> str:
        existing = portfolio.position(expression.instrument_id)
        existing_str = (
            f"qty={existing.quantity:+.2f} entry={existing.avg_entry_price:.4f} "
            f"current={existing.current_price:.4f} parent_hyp={existing.parent_hypothesis_id}"
            if existing else "(none)"
        )
        kc = "\n".join(f"- {c.description}" for c in hypothesis.kill_criteria)
        return (
            f"Verdict: {verdict.decision} (size_mult={verdict.size_multiplier})\n"
            f"Decisive factor: {verdict.decisive_factor}\n"
            f"GuardDecision: {guard.decision} (amended_size_mult={guard.amended_size_multiplier})\n"
            f"Guard rationale: {guard.rationale}\n\n"
            f"Trade expression:\n"
            f"- {expression.direction.value} {expression.instrument_id}\n"
            f"- target_size_pct_nav: {expression.target_size_pct_nav:.4f}\n"
            f"- initial_stop_pct: {expression.initial_stop_pct:.4f}\n"
            f"- horizon_days: {expression.expected_holding_days}\n\n"
            f"Existing position in {expression.instrument_id}: {existing_str}\n\n"
            f"Hypothesis kill criteria (you MUST cite at least one):\n{kc}\n\n"
            f"NAV: {portfolio.nav:.2f}\n"
            f"Open positions: {len(portfolio.positions)}"
        )


def materialize_order(
    *,
    decision: PortfolioDecision,
    expression: TradeExpression,
    hypothesis: Hypothesis,
    guard: GuardDecision,
    portfolio: Portfolio,
    gate_multiplier: float = 1.0,
) -> TradeOrder | None:
    """Turn the agent's PortfolioDecision into an executable TradeOrder.

    Returns None for 'hold' or for `gate_multiplier == 0` (risk-off veto).
    Raises if pricing fails — we fail loudly rather than journalling a
    corrupt order.
    """
    # Defense in depth: even if a future caller bypasses run_portfolio_agent's
    # short-circuit, a hard-vetoed expression must never become an order.
    if guard.decision == "hard_veto":
        if decision.action != "hold":
            log.warning(
                "Suppressing %s order on %s — guard hard-vetoed (rules=%s).",
                decision.action, expression.instrument_id, guard.triggered_rules,
            )
        return None
    if decision.action == "hold":
        return None
    if gate_multiplier <= 0.0:
        log.info(
            "Risk-off gate vetoed %s on %s — emitting no order.",
            decision.action, expression.instrument_id,
        )
        return None

    inst_price = latest(expression.instrument_id).price
    nav = portfolio.nav
    if nav <= 0:
        raise RuntimeError("NAV non-positive — cannot size order")

    notional = decision.quantity_pct_nav * nav * gate_multiplier
    instrument = expression.instrument_id

    # Compute quantity respecting contract multiplier (futures: contracts; FX: notional)
    from castelino.data.instruments import get_instrument
    inst = get_instrument(instrument)
    raw_qty = notional / (inst_price * inst.contract_multiplier)
    quantity = max(round(raw_qty), 1) if inst.contract_multiplier > 1 else round(raw_qty, 4)
    if quantity <= 0:
        log.warning("Computed zero quantity for %s; emitting hold.", instrument)
        return None

    if decision.action in ("close", "trim"):
        existing = portfolio.position(instrument)
        if existing is None:
            log.warning("Asked to %s %s but no open position; skipping.", decision.action, instrument)
            return None
        side = Side.SELL if existing.quantity > 0 else Side.BUY
        otype = OrderType.MARKET_CLOSE if decision.action == "close" else OrderType.TRIM
        qty = abs(existing.quantity) if decision.action == "close" else min(quantity, abs(existing.quantity))
        stop = None
    else:  # open
        side = Side.BUY if expression.direction.value == "long" else Side.SELL
        otype = OrderType.MARKET_OPEN
        qty = quantity
        stop = (
            inst_price * (1 - decision.stop_loss_pct)
            if side == Side.BUY
            else inst_price * (1 + decision.stop_loss_pct)
        )

    return TradeOrder(
        order_id=f"ord-{uuid.uuid4().hex[:10]}",
        instrument_id=instrument,
        order_type=otype,
        side=side,
        quantity=qty,
        reference_price=inst_price,
        parent_hypothesis_id=expression.parent_hypothesis_id,
        parent_expression_id=expression.entry_id,
        stop_loss=stop,
        notes=(
            f"{decision.notes} | kill: {decision.cite_kill_criterion}"
        ),
    )


def run_portfolio_agent(
    *,
    verdict: Verdict,
    guard: GuardDecision,
    expression: TradeExpression,
    hypothesis: Hypothesis,
    portfolio: Portfolio,
    gate_multiplier: float = 1.0,
) -> tuple[PortfolioDecision, TradeOrder | None]:
    """End-to-end: run the LLM, then materialize an order.

    On `hard_veto`, short-circuit: do not call the LLM. Constitutional vetoes
    must be structurally enforced — relying on the prompt to make the LLM
    return 'hold' would let a future prompt regression turn a veto into a
    fill. Instead, emit a synthetic `hold` decision and journal the rationale.
    """
    if guard.decision == "hard_veto":
        decision = PortfolioDecision(
            action="hold",
            quantity_pct_nav=0.0,
            stop_loss_pct=0.0,
            notes=f"Hard-veto by Principles Guard ({', '.join(guard.triggered_rules) or 'unknown'})",
            cite_kill_criterion=(
                hypothesis.kill_criteria[0].description
                if hypothesis.kill_criteria else "n/a"
            ),
        )
        return decision, None

    decision = PortfolioAgent()(
        verdict=verdict,
        guard=guard,
        expression=expression,
        hypothesis=hypothesis,
        portfolio=portfolio,
    )
    try:
        order = materialize_order(
            decision=decision,
            expression=expression,
            hypothesis=hypothesis,
            guard=guard,
            portfolio=portfolio,
            gate_multiplier=gate_multiplier,
        )
    except PricingError as e:
        log.error("pricing failed during order materialization: %s", e)
        order = None
    return decision, order
