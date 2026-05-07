"""Current Event Agent — broad scan: 'what just changed in the world?'.

Inputs: a TriggerRecord and recent news headlines (≤24h).
Output: a `WorldStateBrief` — a compressed, structured summary that downstream
agents can read instead of raw RSS. This is the prompt-injection containment
layer: agents below this point never see un-curated text.
"""

from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.data.leading_indicators import format_catalog_for_prompt
from castelino.memory.schemas import TriggerRecord, WorldStateBrief

SYSTEM_BASE = """\
You are the Current Event Agent for a multi-asset macro hedge fund.

Your only job is to compress the most recent macro-relevant news into a
structured brief. You are a SUMMARIZER, not an analyst.

Hard requirements:
- Cite only headlines and context provided in the user message. Do not speculate.
- List 3–8 headlines, in order of macro materiality.
- Identify any genuine "surprises" — events that would shift consensus.
- Use the detailed source context (when provided) to write a richer, more
  specific summary than the headline alone would allow.
- Populate `source_summaries` with the context blocks (1:1 with headlines) so
  downstream agents can reference the source material.
- Do NOT propose trades, theses, or directional views. That is downstream.

Leading-indicator reads:
- Consult the CANONICAL INDICATOR CATALOG below.
- For each `leading_indicator_read` you output, `indicator_key` MUST match a
  catalog key exactly (backtick id).
- `supporting_headline` MUST be a verbatim copy of one headline line you were
  given (same text as in the bullet list), with no paraphrase.
- Include at most 12 reads; only add a read when the headline evidence clearly
  touches that indicator. If nothing maps, use an empty list.
"""


class CurrentEventAgent(StructuredAgent[WorldStateBrief]):
    name = "current_event"
    output_schema = WorldStateBrief
    tier = "fast"

    def system_prompt(self) -> str:
        return f"{SYSTEM_BASE}\n{format_catalog_for_prompt()}"

    def user_prompt(
        self,
        *,
        trigger: TriggerRecord,
        recent_headlines: list[str],
        source_summaries: list[str] | None = None,
    ) -> str:
        source_summaries = source_summaries or []

        lines: list[str] = []
        for i, h in enumerate(recent_headlines[:30]):
            lines.append(f"{i + 1}. {h}")
            if i < len(source_summaries) and source_summaries[i]:
                lines.append(f"   Context: {source_summaries[i]}")
        headlines_block = "\n".join(lines) or "- (none)"

        return (
            f"Trigger that fired the pipeline:\n"
            f"- source: {trigger.source.value}\n"
            f"- headline: {trigger.headline}\n"
            f"- significance: {trigger.significance}\n"
            f"- one-sentence reason: {trigger.one_sentence_reason}\n"
            f"- asset_classes_affected: {trigger.asset_classes_affected}\n\n"
            f"Recent headlines with context (last 24h):\n{headlines_block}\n\n"
            f"Set parent_trigger_id = {trigger.entry_id!r}.\n"
            f"Produce a WorldStateBrief."
        )
