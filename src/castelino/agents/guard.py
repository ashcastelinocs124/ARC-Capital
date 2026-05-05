"""Principles Guard — hybrid (deterministic veto + LLM soft-rule judgment).

Hard rules (H1–H5 in core_principles.md) are checked in pure Python. A hard
violation produces a `hard_veto` GuardDecision that the Portfolio Agent must
honor. Soft rules are evaluated by the LLM with the full trade context.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from castelino.agents.base import StructuredAgent
from castelino.config import get_settings
from castelino.data.instruments import AssetClass, get_instrument
from castelino.execution.portfolio import Portfolio
from castelino.execution.pricing import PricingError, latest
from castelino.memory import io as memio
from castelino.memory.schemas import (
    GuardDecision,
    Hypothesis,
    PrincipleWarning,
    TradeExpression,
    Verdict,
)

log = logging.getLogger(__name__)


# ───────────────────────── deterministic hard checks ──────────────────────


def check_hard_rules(
    expression: TradeExpression,
    verdict: Verdict,
    portfolio: Portfolio,
) -> list[PrincipleWarning]:
    """Return all hard-rule violations triggered by this proposed trade.

    Empty list = clean. Non-empty = `hard_veto` regardless of LLM opinion.
    """
    cfg = get_settings()
    risk = cfg.risk
    warnings: list[PrincipleWarning] = []

    inst = get_instrument(expression.instrument_id)
    nav = portfolio.nav
    if nav <= 0:
        warnings.append(_w("H_NAV", "hard", f"NAV non-positive ({nav})", expression))
        return warnings

    # H1.1 — single position size cap (using verdict-modified target)
    proposed_size = expression.target_size_pct_nav * verdict.size_multiplier
    if proposed_size > risk.position_max_pct_nav + 1e-9:
        warnings.append(
            _w(
                "H1",
                "hard",
                f"Proposed size {proposed_size:.4f} exceeds {risk.position_max_pct_nav:.4f} cap.",
                expression,
            )
        )

    # H1.2 — asset-class concentration
    by_class = {ac: v for ac, v in portfolio.exposure_by_class().items()}
    add = proposed_size * nav
    new_class_exp = by_class.get(inst.asset_class, 0.0) + add
    if new_class_exp / nav > risk.asset_class_max_pct_gross + 1e-9:
        warnings.append(
            _w(
                "H1",
                "hard",
                f"{inst.asset_class.value} concentration after fill = "
                f"{new_class_exp/nav:.3f} > cap {risk.asset_class_max_pct_gross:.3f}",
                expression,
            )
        )

    # H1.3 — drawdown freeze
    dd = _drawdown(portfolio)
    if dd > risk.drawdown_freeze_pct:
        warnings.append(
            _w(
                "H1",
                "hard",
                f"Drawdown {dd:.3f} exceeds freeze threshold {risk.drawdown_freeze_pct}",
                expression,
            )
        )

    # H2 — liquidity
    if inst.avg_daily_volume_usd is not None:
        if inst.avg_daily_volume_usd < risk.liquidity_min_adv_usd:
            warnings.append(
                _w(
                    "H2",
                    "hard",
                    f"ADV {inst.avg_daily_volume_usd:.0f} below {risk.liquidity_min_adv_usd:.0f}",
                    expression,
                )
            )
        if (proposed_size * nav) > inst.avg_daily_volume_usd * risk.liquidity_max_pct_adv:
            warnings.append(
                _w(
                    "H2",
                    "hard",
                    f"Position notional {proposed_size*nav:.0f} > "
                    f"{risk.liquidity_max_pct_adv*100:.1f}% of ADV {inst.avg_daily_volume_usd:.0f}",
                    expression,
                )
            )

    # H3 — VIX circuit breaker
    try:
        vix_px = latest("VIX").price
        if vix_px > risk.vix_circuit_breaker:
            new_gross = portfolio.gross_exposure + add
            if new_gross / nav > 0.50 + 1e-9:
                warnings.append(
                    _w(
                        "H3",
                        "hard",
                        f"VIX={vix_px:.1f} > {risk.vix_circuit_breaker}; gross would be {new_gross/nav:.3f} > 0.50",
                        expression,
                    )
                )
    except PricingError as e:
        log.warning("VIX unavailable, skipping H3 circuit-breaker check: %s", e)

    # H3.2 — 5-day rolling P&L freeze
    if _five_day_pnl_pct(portfolio) < risk.five_day_pnl_freeze_pct:
        # Check the 3-flat-or-positive recovery condition
        if not _three_consecutive_recovery_days(portfolio):
            warnings.append(
                _w(
                    "H3",
                    "hard",
                    f"5-day P&L below {risk.five_day_pnl_freeze_pct:.2%} and no 3-day recovery.",
                    expression,
                )
            )

    # H5 — mandatory linkage
    if not expression.parent_hypothesis_id:
        warnings.append(_w("H5", "hard", "Missing parent_hypothesis_id", expression))

    return warnings


def _w(rule_id: str, severity, description: str, expression: TradeExpression) -> PrincipleWarning:
    return PrincipleWarning(
        rule_id=rule_id,
        severity=severity,
        description=description,
        parent_expression_id=expression.entry_id,
    )


def _drawdown(portfolio: Portfolio) -> float:
    if not portfolio.nav_history:
        return 0.0
    peak = max(s.nav for s in portfolio.nav_history)
    if peak <= 0:
        return 0.0
    return (peak - portfolio.nav) / peak


def _five_day_pnl_pct(portfolio: Portfolio) -> float:
    if len(portfolio.nav_history) < 6:
        return 0.0
    snaps = portfolio.nav_history[-6:]
    return (snaps[-1].nav - snaps[0].nav) / snaps[0].nav


def _three_consecutive_recovery_days(portfolio: Portfolio) -> bool:
    if len(portfolio.nav_history) < 4:
        return False
    snaps = portfolio.nav_history[-4:]
    return all(snaps[i + 1].nav >= snaps[i].nav for i in range(3))


# ───────────────────────── soft-rule LLM layer ────────────────────────────


SYSTEM = """\
You are the Principles Guard's soft-rule layer. The hard rules have already
been checked in deterministic Python and any hard violation has been recorded.
Your job is to evaluate the SOFT rules (S1–S6 in core_principles.md):

- S1: no averaging into a thesis-broken trade
- S2: ≤2 active trades in same regime hypothesis
- S3: 24h cooling-off after closing the same instrument at a loss
- S4: every trade must cite a kill criterion in its open notes
- S5: 3 consecutive losses in a thesis category → flag for review
- S6: acknowledge any LT lesson that contradicts the trade

Return a GuardDecision with one of:
- 'approved' (no soft violations, or violations defensible — explain in rationale)
- 'soft_warning' (proceed but log warnings)
- 'amended' (proceed with reduced size_multiplier — set amended_size_multiplier)
- 'hard_veto' (only if asked to escalate, or if hard violations were already passed in)

If 3+ soft rules fire on a single trade, escalate to 'hard_veto' regardless.
Cite the rule_ids you triggered in `triggered_rules`.
"""


class GuardSoftAgent(StructuredAgent[GuardDecision]):
    name = "guard_soft"
    output_schema = GuardDecision
    tier = "reasoning"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self,
        *,
        verdict: Verdict,
        expression: TradeExpression,
        hypothesis: Hypothesis,
        portfolio: Portfolio,
        hard_warnings: list[PrincipleWarning],
    ) -> str:
        principles = memio.read_principles()
        recent_trades = "\n".join(
            f"- {p.instrument_id}: qty={p.quantity:+.2f} parent_hyp={p.parent_hypothesis_id}"
            for p in portfolio.positions
        ) or "- (none)"
        recent_closed = memio.latest_n(kind="TradeEvent", n=10)
        closed = "\n".join(
            f"- {t.event_type} {t.instrument_id} pnl={t.realized_pnl:.2f}"
            for t in recent_closed
        ) or "- (none)"
        kill_lines = "\n".join(f"- {kc.description}" for kc in hypothesis.kill_criteria)
        hard = "\n".join(f"- [{w.rule_id}] {w.description}" for w in hard_warnings) or "- (none)"
        return (
            f"Verdict: {verdict.decision} (size_mult={verdict.size_multiplier})\n"
            f"Trade: {expression.direction.value} {expression.instrument_id} "
            f"size={expression.target_size_pct_nav:.4f}\n\n"
            f"Hypothesis: {hypothesis.thesis}\n"
            f"Regime: {hypothesis.regime.value}\n"
            f"Kill criteria:\n{kill_lines}\n\n"
            f"Hard-rule violations (already determined):\n{hard}\n\n"
            f"Open positions:\n{recent_trades}\n\n"
            f"Recent fills:\n{closed}\n\n"
            f"Constitution:\n{principles[:2500]}\n\n"
            f"Set parent_verdict_id = {verdict.entry_id!r}."
        )


# ───────────────────────── public entry point ─────────────────────────────


def run_guard(
    *,
    verdict: Verdict,
    expression: TradeExpression,
    hypothesis: Hypothesis,
    portfolio: Portfolio,
) -> GuardDecision:
    """End-to-end guard pass: hard rules → if clean, LLM soft rules."""
    hard = check_hard_rules(expression, verdict, portfolio)
    if hard:
        # Hard veto — don't even spend an LLM call.
        return GuardDecision(
            parent_verdict_id=verdict.entry_id,
            decision="hard_veto",
            triggered_rules=[w.rule_id for w in hard],
            rationale=(
                f"Hard-rule violations: "
                + "; ".join(f"[{w.rule_id}] {w.description}" for w in hard)
            ),
            warnings=hard,
        )
    decision = GuardSoftAgent()(
        verdict=verdict,
        expression=expression,
        hypothesis=hypothesis,
        portfolio=portfolio,
        hard_warnings=hard,
    )
    return decision


def write_exposure_snapshot_for_guard(portfolio: Portfolio, path: Path | None = None) -> None:
    """Helper used by tests / CLI: snapshot exposure for the Guard to read."""
    cfg = get_settings()
    p = path or (cfg.resolved_paths.data / "exposure_snapshot.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    by_class = {ac.value: portfolio.exposure_by_class().get(ac, 0.0) for ac in AssetClass}
    snap = {
        "timestamp": datetime.now(UTC).isoformat(),
        "nav": portfolio.nav,
        "gross_exposure": portfolio.gross_exposure,
        "exposure_by_class": by_class,
    }
    with p.open("w") as f:
        json.dump(snap, f, indent=2)
