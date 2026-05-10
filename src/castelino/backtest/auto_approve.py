"""Deterministic auto-approval policy for the historical backtest.

Replaces HITL gates during a backtest run. Conservative on purpose — a real
human reviewer presumably catches more edge cases. Numbers from this policy
are a *floor* on what production would do, not a ceiling.

Policy summary:

  Gate 1 (POST_HYPOTHESIS):
    APPROVE iff conviction in {medium, high}.
    REJECT  otherwise (low-conviction theses skip the wave).

  Gate 2 (POST_DEBATE):
    APPROVE iff:
      decision in {"proceed", "modify"}
      AND (decision != "modify" OR size_multiplier >= 0.5)
      AND dissent != "high"
    REJECT  otherwise.

The hook is wired in `orchestrator.approval.ApprovalQueue.submit()` —
when `BACKTEST_AS_OF` is set, every submitted item is instantly resolved
according to the policy, so `wait_for_resolution()` returns on the first
poll iteration.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from castelino.orchestrator.approval import ApprovalItem

log = logging.getLogger(__name__)


def _decide_post_hypothesis(payload: dict) -> tuple[bool, str]:
    """Return (approve?, reason)."""
    conviction = str(payload.get("conviction", "")).lower()
    if conviction in ("medium", "high"):
        return True, f"auto-approve: conviction={conviction}"
    return False, f"auto-reject: low/unknown conviction ({conviction!r})"


def _decide_post_debate(payload: dict) -> tuple[bool, str]:
    decision = str(payload.get("decision", "")).lower()
    if decision not in ("proceed", "modify"):
        return False, f"auto-reject: verdict was {decision!r}"
    if decision == "modify":
        size_mult = float(payload.get("size_multiplier", 0.0) or 0.0)
        if size_mult < 0.5:
            return False, f"auto-reject: size_multiplier={size_mult:.2f} < 0.5"
    dissent = str(payload.get("dissent", "")).lower()
    if "high" in dissent:
        return False, f"auto-reject: dissent={dissent!r}"
    return True, f"auto-approve: decision={decision}"


def apply_policy(item: "ApprovalItem") -> None:
    """Mutate `item` in place: set status, notes/rejection_reason, resolved_at.

    Idempotent — already-resolved items are left alone.
    """
    from castelino.orchestrator.approval import ApprovalStatus, GateType

    if item.status != ApprovalStatus.PENDING:
        return

    if item.gate == GateType.POST_HYPOTHESIS:
        approve, reason = _decide_post_hypothesis(item.payload)
    elif item.gate == GateType.POST_DEBATE:
        approve, reason = _decide_post_debate(item.payload)
    else:
        approve, reason = False, f"auto-reject: unknown gate {item.gate!r}"

    item.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    item.resolved_at = datetime.now(UTC).isoformat()
    item.notes = reason
    if not approve:
        item.rejection_reason = reason
    log.info(
        "[auto-approve] %s %s → %s (%s)",
        item.gate, item.entry_id, item.status, reason,
    )
