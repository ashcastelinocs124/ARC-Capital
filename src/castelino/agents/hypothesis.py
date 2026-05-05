"""Macro Hypothesis Agent — form a falsifiable view.

Reads world state + ST + LT + core_principles. Outputs a `Hypothesis` with
mandatory `kill_criteria`. Without kill criteria a thesis is not allowed.
"""

from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.memory import io as memio
from castelino.memory.schemas import Hypothesis, WorldStateBrief

SYSTEM = """\
You are the Macro Hypothesis Agent at a multi-asset macro fund.

Your job: form ONE falsifiable macro thesis from the world-state brief.

Non-negotiable rules:
1. The thesis must be falsifiable. State at least one `kill_criterion` — a
   specific, measurable condition that, if met, kills the thesis.
2. Pick a horizon between 1 and 90 days. Days-to-weeks is the sweet spot.
3. Conviction must reflect evidence quality, not enthusiasm.
4. Cite contradicting evidence honestly. If you cannot articulate a counter-view,
   your conviction must be 'low'.
5. Read the long-term journal lessons; if a recurring lesson contradicts your
   thesis, address it explicitly in `rationale` or downgrade conviction.

This is a TOP-DOWN macro thesis, not a stock pick. Frame it in regime terms
("disinflation continues", "USD top is in", "energy supply shock"), not company
terms ("AAPL beats earnings").
"""


class HypothesisAgent(StructuredAgent[Hypothesis]):
    name = "hypothesis"
    output_schema = Hypothesis
    tier = "reasoning"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, world_state: WorldStateBrief) -> str:
        principles = memio.read_principles()
        recent_hypotheses = [
            f"- {e.thesis} (regime={e.regime.value}, conviction={e.conviction.value})"
            for e in memio.latest_n(kind="Hypothesis", n=5)
        ]
        long_term_lessons = [
            f"- [{e.category}] {e.title}: {e.body}"
            for e in memio.read_long_term()[-10:]
        ]
        return (
            f"World-state brief:\n{world_state.summary}\n\n"
            f"Headlines: {world_state.headlines}\n"
            f"Surprises: {world_state.surprises}\n"
            f"Macro signals: {world_state.macro_signals}\n\n"
            f"Recent hypotheses (last 5):\n"
            + ("\n".join(recent_hypotheses) or "- (none)")
            + "\n\nLong-term lessons:\n"
            + ("\n".join(long_term_lessons) or "- (none)")
            + "\n\nConstitutional principles:\n"
            + (principles[:2000] if principles else "(none)")
            + f"\n\nSet parent_trigger_id = {world_state.parent_trigger_id!r} and "
              f"parent_world_state_id = {world_state.entry_id!r}."
        )
