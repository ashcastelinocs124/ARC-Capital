"""Web Research Agent — instrument-specific news / sentiment.

The LLM is constrained to summarize whatever headlines the trigger layer fed
in plus any provided context. It does NOT fetch new content — that would be
prompt-injection-prone. The trigger / news layer is the only place we ingest
raw text.
"""

from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.memory.schemas import TradeExpression, WebResearch, WorldStateBrief

SYSTEM = """\
You are the Web Research interpreter. Summarize the supplied headlines and
catalyst notes for the proposed instrument.

Rules:
- Only use information present in the user message. Do not invent news.
- Sentiment must reflect what the headlines actually say, not your prior.
- `catalysts` are forward-looking events (earnings, FOMC, OPEC) only — not
  past news.
- Keep `summary` to 2-3 sentences.
"""


class WebResearchAgent(StructuredAgent[WebResearch]):
    name = "web"
    output_schema = WebResearch
    tier = "fast"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self,
        *,
        expression: TradeExpression,
        world_state: WorldStateBrief,
    ) -> str:
        bullets = "\n".join(f"- {h}" for h in world_state.headlines) or "- (none)"
        return (
            f"Proposed trade: {expression.direction.value} {expression.instrument_id}\n\n"
            f"World-state summary: {world_state.summary}\n\n"
            f"Headlines available:\n{bullets}\n\n"
            f"Macro signals: {world_state.macro_signals}\n"
            f"Surprises: {world_state.surprises}\n\n"
            "Produce a WebResearch report scoped to the proposed instrument."
        )


def run_web(expression: TradeExpression, world_state: WorldStateBrief) -> WebResearch:
    return WebResearchAgent()(expression=expression, world_state=world_state)
