from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.agents.update.models import DailyUpdate, MarketSnapshot
from castelino.config import get_settings

SYSTEM = """You are the daily market briefing analyst for ARC Research, a macro fund.
Explain what happened in economic data and across asset classes and sectors, and why.

Rules:
- Cite figures ONLY from the snapshot, always with their unit (%, bp or pp). Never invent or
  estimate a number. If something is not in the snapshot, say it is unavailable.
- Link the data to the price action, and link both to the running themes in memory.
- Report divergences between short-term and long-term sector trends (e.g. a 1-month pullback
  inside a 12-month uptrend) and say whether it looks like a pullback or a reversal.
- Explain any change in the regime predictions using snapshot.prediction. A model whose gate
  decision is "kept" did not change: say so and why, do not present its refit as the forecast.
- State snapshot.data_gaps and snapshot.model_note plainly if present.
- themes_touched titles must match existing memory titles EXACTLY. Propose at most 2 new themes,
  importance 1-5 (5 = always relevant). Write one short read per sector in snapshot.sectors.
- Be concise and concrete. No investment advice."""


class UpdateAgent(StructuredAgent[DailyUpdate]):
    name = "update_agent"
    output_schema = DailyUpdate

    def __init__(self) -> None:
        cfg = get_settings().update_agent
        self.tier = cfg.model_tier
        self.max_output_tokens = cfg.max_output_tokens

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, snapshot: MarketSnapshot, memory_md: str,
                    long_term_md: str, guard_errors: list[str] | None = None) -> str:
        parts = [
            f"## Snapshot ({snapshot.date})\n{snapshot.model_dump_json(indent=2)}",
            f"## Short-term memory (MEMORY.md)\n{memory_md or '(empty)'}",
            f"## Long-term memory (long-term.md)\n{long_term_md or '(empty)'}",
        ]
        if guard_errors:
            parts.append(
                "## Correction\nYour previous draft cited figures that are not in the snapshot: "
                f"{', '.join(guard_errors)}. Rewrite using only figures from the snapshot.")
        return "\n\n".join(parts)


def write_update(snapshot: MarketSnapshot, memory_md: str, long_term_md: str,
                 guard_errors: list[str] | None = None) -> DailyUpdate:
    return UpdateAgent()(snapshot=snapshot, memory_md=memory_md,
                         long_term_md=long_term_md, guard_errors=guard_errors)
