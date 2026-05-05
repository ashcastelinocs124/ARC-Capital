"""Debate Agent — adjudicate Bull vs Bear, return a Verdict."""

from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.memory.schemas import (
    BearCase,
    BullCase,
    Hypothesis,
    Verdict,
)

SYSTEM = """\
You are the Debate adjudicator. Read Bull and Bear cases on the same facts and
return ONE structured Verdict.

Decision rules:
- 'proceed' = Bull wins clearly; full size or close to it.
- 'reject' = Bear wins clearly; do not trade.
- 'modify' = neither side dominant; trade with a reduced size_multiplier.
- size_multiplier ∈ [0.0, 2.0]. Use 0.5 to halve, 0.0 only with 'reject'.
- The decisive_factor MUST cite the SPECIFIC argument that tipped your
  decision. "Bull case stronger overall" is not acceptable.
- If both sides have meaningful arguments, record the loser's strongest point
  in `dissent`.

Be decisive. Indecision is itself a 'reject' — better to skip than to size at
0.5x out of confusion.
"""


class DebateAgent(StructuredAgent[Verdict]):
    name = "debate"
    output_schema = Verdict
    tier = "reasoning"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self,
        *,
        bull: BullCase,
        bear: BearCase,
        hypothesis: Hypothesis,
    ) -> str:
        bull_args = "\n".join(f"- {a}" for a in bull.arguments)
        bear_args = "\n".join(f"- {a}" for a in bear.arguments)
        return (
            f"Parent hypothesis: {hypothesis.thesis}\n"
            f"Conviction at hypothesis stage: {hypothesis.conviction.value}\n\n"
            f"BULL CASE (confidence={bull.confidence.value}):\n"
            f"Strongest: {bull.strongest_argument}\n"
            f"All:\n{bull_args}\n\n"
            f"BEAR CASE (confidence={bear.confidence.value}):\n"
            f"Strongest: {bear.strongest_argument}\n"
            f"All:\n{bear_args}\n\n"
            f"Set parent_expression_id = {bull.parent_expression_id!r}, "
            f"parent_bull_id = {bull.entry_id!r}, "
            f"parent_bear_id = {bear.entry_id!r}."
        )
