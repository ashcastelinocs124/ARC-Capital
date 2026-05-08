"""Risk-Off Gate — defensive overlay between Constitutional Guard and Portfolio.

Reads `data/risk_off_forecast.json` (P(SPY drawdown >5% next month)) and
applies a four-tier policy to each trade:

| prob_risk_off  | risk-on trade        | defensive trade |
|----------------|----------------------|-----------------|
| < 0.3          | pass (1.0x)          | pass (1.0x)     |
| 0.3 – 0.6      | downsize (0.5x)      | pass (1.0x)     |
| 0.6 – 0.85     | veto (0.0x)          | pass (1.0x)     |
| ≥ 0.85         | amplify (1.3x)       | pass (1.0x)     |

The capitulation tier (≥ 0.85) flips the gate from defensive to contrarian —
historically forward equity returns are best at extreme fear, and the gate
adds size on risk-on trades.

Output is a `GateDecision` per trade. Multiplier flows into the existing
sizing formula in the Portfolio Agent.

Deterministic, no LLM call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from castelino.config import get_settings
from castelino.data.instruments import INSTRUMENTS
from castelino.forecast.risk_off import read_forecast

log = logging.getLogger(__name__)


@dataclass
class GateDecision:
    action: Literal["pass", "downsize", "veto", "amplify"]
    size_multiplier: float
    prob_risk_off: float
    rationale: str

    @property
    def vetoed(self) -> bool:
        return self.action == "veto" or self.size_multiplier == 0.0


def _instrument_is_risk_on(instrument_id: str) -> bool:
    """Look up risk_on classification. Default to True for unknown instruments."""
    inst = INSTRUMENTS.get(instrument_id)
    if inst is None:
        log.warning("unknown instrument %r at risk gate, treating as risk-on", instrument_id)
        return True
    return inst.risk_on


def evaluate(instrument_id: str) -> GateDecision:
    """Evaluate a single trade against the current risk-off forecast.

    If no forecast exists, the gate passes everything through unchanged
    (fail-open — better to trade than to silently block).
    """
    cfg = get_settings().risk_gate
    forecast = read_forecast()

    if forecast is None:
        return GateDecision(
            action="pass",
            size_multiplier=1.0,
            prob_risk_off=0.0,
            rationale="no risk_off forecast — gate fail-open",
        )

    p = forecast.prob_risk_off
    is_risk_on = _instrument_is_risk_on(instrument_id)

    # Defensive trades always pass — the gate is for risk assets only.
    if not is_risk_on:
        return GateDecision(
            action="pass",
            size_multiplier=1.0,
            prob_risk_off=p,
            rationale=f"P={p:.2f}, defensive instrument {instrument_id} — pass",
        )

    # Risk-on trades go through the tier ladder.
    if p < cfg.caution_min:
        return GateDecision(
            action="pass",
            size_multiplier=1.0,
            prob_risk_off=p,
            rationale=f"P={p:.2f} < {cfg.caution_min} — calm tier",
        )

    if p < cfg.danger_min:
        return GateDecision(
            action="downsize",
            size_multiplier=cfg.caution_size_mult,
            prob_risk_off=p,
            rationale=(
                f"P={p:.2f} in caution tier "
                f"[{cfg.caution_min}, {cfg.danger_min}) — risk-on cut to "
                f"{cfg.caution_size_mult}x"
            ),
        )

    if p < cfg.capitulation_min:
        return GateDecision(
            action="veto",
            size_multiplier=0.0,
            prob_risk_off=p,
            rationale=(
                f"P={p:.2f} in danger tier "
                f"[{cfg.danger_min}, {cfg.capitulation_min}) — risk-on vetoed"
            ),
        )

    return GateDecision(
        action="amplify",
        size_multiplier=cfg.capitulation_amplify,
        prob_risk_off=p,
        rationale=(
            f"P={p:.2f} ≥ {cfg.capitulation_min} — capitulation tier, "
            f"contrarian amplify {cfg.capitulation_amplify}x"
        ),
    )
