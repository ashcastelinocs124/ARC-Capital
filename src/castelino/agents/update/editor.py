"""Editor: writes the Morning Note from the findings and picks which ones get a chart."""

from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.agents.update.models import Fact, Finding, MorningNote
from castelino.config import get_settings

SYSTEM = """You are the editor of ARC Research's Morning Note, a short professional note for
macro investors. From the findings, write:
- headline: one sentence, the day's main story.
- takeaways: exactly 3 one-sentence bullets.
- items: 3 to {items} items ranked by importance (rank 1 = most important). Each has a short
  title, a body, the finding ids it rests on, and chart = one of ITS OWN finding ids marked
  [chartable], or null. Spread items across macro, news and alt when the day allows; never pad.
- Each item body is ONE paragraph of 80-120 words covering: what happened; how it
  compares with the prior reading (use the prior values in the evidence, e.g. "up from 3.54%");
  and why it matters for markets (rates, equities, the Fed path), linking to other items where
  they connect.
  Headline and takeaways stay short.
Rules:
- Use ONLY figures that appear in the evidence of the findings an item cites (headline and
  takeaways: any finding), always with their unit (%, bp or pp). Never invent, round differently
  or compute a new number. Make no claims about history the evidence doesn't show (e.g. "highest
  in a year") unless the evidence states it.
- themes_touched titles must match existing memory titles EXACTLY. At most 2 new_themes,
  importance 1-5 (5 = always relevant).
- Write about today's findings. Memory is background for comparison only, never a topic on
  its own: don't revive an old theme unless today's findings move it.
- Describe, don't recommend. No investment advice."""


class UpdateEditor(StructuredAgent[MorningNote]):
    name = "update_editor"
    output_schema = MorningNote
    tier = "reasoning"
    items = 5

    def __init__(self) -> None:
        cfg = get_settings().update_agent
        self.model = cfg.editor_model
        self.max_output_tokens = cfg.max_output_tokens
        self.items = cfg.items

    def system_prompt(self) -> str:
        return SYSTEM.format(items=self.items)

    def user_prompt(
        self,
        *,
        findings: list[Finding],
        facts: list[Fact],
        memory_md: str,
        long_term_md: str,
        guard_errors: list[str] | None = None,
    ) -> str:
        by_id = {f.id: f for f in facts}
        blocks = []
        for f in findings:
            evidence = " | ".join(by_id[i].text for i in f.fact_ids if i in by_id)
            tag = " [chartable]" if f.series else ""
            blocks.append(
                f"[{f.id}] ({f.agent}){tag} {f.claim}\n  evidence: {evidence}"
                f"\n  source: {f.source_title}"
            )
        parts = [
            "## Findings\n" + "\n".join(blocks),
            f"## Short-term memory (MEMORY.md)\n{memory_md or '(empty)'}",
            f"## Long-term memory (long-term.md)\n{long_term_md or '(empty)'}",
        ]
        if guard_errors:
            parts.append(
                "## Correction\nYour previous draft failed these checks: "
                f"{'; '.join(guard_errors)}. Fix them using only figures from the evidence."
            )
        return "\n\n".join(parts)


def write_note(
    findings: list[Finding],
    facts: list[Fact],
    memory_md: str,
    long_term_md: str,
    guard_errors: list[str] | None = None,
) -> MorningNote:
    return UpdateEditor()(
        findings=findings,
        facts=facts,
        memory_md=memory_md,
        long_term_md=long_term_md,
        guard_errors=guard_errors,
    )
