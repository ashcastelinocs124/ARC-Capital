"""Asset Selection Agent — pick 1-3 best vehicles for the thesis.

Considers: existing book correlation, vehicle hit-rates from LT memory, and
the universe of tradable instruments.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from castelino.agents.base import StructuredAgent
from castelino.data.instruments import tradable_universe
from castelino.execution.portfolio import Portfolio
from castelino.memory import io as memio
from castelino.memory.schemas import Hypothesis, TradeExpression


class AssetSelectionOutput(BaseModel):
    """Wrapper schema — OpenAI structured output requires a single root model."""

    expressions: List[TradeExpression] = Field(min_length=1, max_length=3)
    rationale_overall: str


SYSTEM = """\
You are the Asset Selection Agent. Given a macro hypothesis, choose 1–3
specific tradable instruments that best express it.

Rules:
- Only use instruments from the tradable universe given in the user message.
- Diversify across asset classes when the thesis allows — multi-asset macro is
  the point of this fund.
- Read the open positions; do not propose trades that double up an existing
  exposure unless the thesis specifically argues for it.
- Each expression must include direction (long/short), expected holding days,
  target size as % of NAV (max 5%), and an initial stop as a % from entry.
- Prefer ETFs over single names when the thesis is regime-level.
- When MACRO REGIME CONTEXT is given in the user message, **prioritize**
  instruments from the preferred ETF / sector hints when they fit the
  hypothesis. You may pick other universe names only if the thesis clearly
  requires a different expression (explain in `rationale_overall`).
- Set `parent_hypothesis_id` on every TradeExpression.
"""


class AssetSelectionAgent(StructuredAgent[AssetSelectionOutput]):
    name = "asset_selection"
    output_schema = AssetSelectionOutput
    tier = "reasoning"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self,
        *,
        hypothesis: Hypothesis,
        portfolio: Portfolio,
        macro_context: str = "",
    ) -> str:
        universe = "\n".join(
            f"- {i.instrument_id} ({i.asset_class.value}): {i.description}"
            for i in tradable_universe()
        )
        open_positions = (
            "\n".join(
                f"- {p.instrument_id}: qty={p.quantity:+.2f} @ {p.avg_entry_price:.4f} "
                f"({p.asset_class.value})"
                for p in portfolio.positions
            )
            or "- (none)"
        )
        lt_vehicle = "\n".join(
            f"- {e.title}: {e.body}"
            for e in memio.read_long_term()
            if e.category == "vehicle_preference"
        ) or "- (none)"
        return (
            f"MACRO REGIME CONTEXT:\n{macro_context}\n\n"
            f"Hypothesis (regime={hypothesis.regime.value}, conviction={hypothesis.conviction.value}):\n"
            f"{hypothesis.thesis}\n\n"
            f"Kill criteria:\n"
            + "\n".join(f"- {kc.description}" for kc in hypothesis.kill_criteria)
            + f"\n\nHorizon: {hypothesis.horizon_days} days. Rationale: {hypothesis.rationale}\n\n"
            f"Tradable universe:\n{universe}\n\n"
            f"Current open positions:\n{open_positions}\n\n"
            f"Long-term vehicle preferences:\n{lt_vehicle}\n\n"
            f"Set parent_hypothesis_id = {hypothesis.entry_id!r} on every expression."
        )
