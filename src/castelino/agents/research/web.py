"""Web Research Agent — instrument-specific news / sentiment.

The LLM is constrained to summarize whatever headlines the trigger layer fed
in plus any provided context. It does NOT fetch new content — that would be
prompt-injection-prone. The trigger / news layer is the only place we ingest
raw text.

OpenBB news supplements the trigger-layer headlines when available.
"""

from __future__ import annotations

import logging

from castelino.agents.base import StructuredAgent
from castelino.data.openbb_adapter import OpenBBError, get_adapter
from castelino.memory.schemas import TradeExpression, WebResearch, WorldStateBrief

log = logging.getLogger(__name__)


def _fetch_openbb_news(query: str, limit: int = 10) -> list[str]:
    """Fetch news headlines via OpenBB. Returns empty list on failure."""
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        articles = adapter.news(query=query, limit=limit)
        return [a.get("title", "") for a in articles if a.get("title")]
    except (OpenBBError, Exception) as e:
        log.debug("OpenBB news fetch failed for %r: %s", query, e)
        return []


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
        li = "\n".join(
            f"- [{r.indicator_key}] {r.read} (headline: {r.supporting_headline})"
            for r in world_state.leading_indicator_reads
        ) or "- (none)"
        return (
            f"Proposed trade: {expression.direction.value} {expression.instrument_id}\n\n"
            f"World-state summary: {world_state.summary}\n\n"
            f"Headlines available:\n{bullets}\n\n"
            f"Macro signals: {world_state.macro_signals}\n"
            f"Surprises: {world_state.surprises}\n"
            f"Leading indicator reads:\n{li}\n\n"
            "Produce a WebResearch report scoped to the proposed instrument."
        )


def run_web(expression: TradeExpression, world_state: WorldStateBrief) -> WebResearch:
    # Supplement trigger-layer headlines with OpenBB news when available
    obb_headlines = _fetch_openbb_news(expression.instrument_id, limit=10)
    if obb_headlines:
        # Deduplicate — avoid repeating headlines already in world_state
        existing = set(world_state.headlines)
        new_headlines = [h for h in obb_headlines if h not in existing]
        if new_headlines:
            world_state = world_state.model_copy(
                update={"headlines": list(world_state.headlines) + new_headlines}
            )

    return WebResearchAgent()(expression=expression, world_state=world_state)
