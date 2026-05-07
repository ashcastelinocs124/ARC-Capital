"""News significance classifier — single fast LLM call, batched.

Headlines come in with a free-form title; out comes a 0-1 materiality score,
directional growth/inflation signals, a list of asset classes affected, and a
one-sentence reason. Threshold checks live in `runner.py`.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

from castelino.agents.base import StructuredAgent
from castelino.triggers.news import NewsHeadline


class HeadlineScore(BaseModel):
    headline_id: str
    title: str
    materiality: float = Field(ge=0.0, le=1.0)
    asset_classes_affected: List[str] = Field(default_factory=list)
    one_sentence_reason: str
    growth_direction: Literal["up", "down", "neutral"] = "neutral"
    inflation_direction: Literal["up", "down", "neutral"] = "neutral"


class SignificanceBatch(BaseModel):
    """Wrapper schema — OpenAI structured output requires one root model."""

    scores: List[HeadlineScore]


SYSTEM = """\
You are a tough macro-news classifier for a multi-asset hedge fund.

Score each headline on materiality 0.0–1.0 for systematic macro positioning:
- 0.0–0.3: routine corporate news, single-stock chatter, repeated story → DROP.
- 0.3–0.5: mildly interesting context but not actionable.
- 0.5–0.7: notable surprise or sector-level mover, log only.
- 0.7–0.9: would meaningfully shift cross-asset positioning if true.
- 0.9–1.0: regime-changing surprise (e.g. unscheduled FOMC action, war, default).

Be HARSH. False positives pollute institutional memory. When in doubt, score
≤ 0.4. The fund operates on REAL macro events — central-bank actions, releases,
geopolitical breaks — not on Bloomberg's daily celebrity carousel.

For each headline:
- `headline_id` and `title` MUST match the input verbatim.
- `asset_classes_affected` from {equity, bond_etf, commodity_etf, fx, futures}.
- `one_sentence_reason` ≤ 120 chars.
- `growth_direction`: does this headline push GROWTH expectations up, down, or
  neutral? "up" = expansionary (strong data, stimulus, hiring). "down" =
  contractionary (weak data, layoffs, tightening). Most headlines are neutral
  on at least one dimension.
- `inflation_direction`: does this headline push INFLATION expectations up,
  down, or neutral? "up" = price pressures rising (tariffs, supply shock, wage
  growth). "down" = disinflationary (weak demand, rate hikes, commodity crash).

Process headlines independently — do not cross-reference them.
"""


class SignificanceClassifier(StructuredAgent[SignificanceBatch]):
    name = "significance"
    output_schema = SignificanceBatch
    tier = "significance"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, headlines: list[NewsHeadline]) -> str:
        bullets = "\n".join(
            f"- id={h.id} | {h.title}" for h in headlines
        )
        return (
            f"Score these headlines:\n{bullets}\n\n"
            "Return one HeadlineScore per input headline; preserve order."
        )


def score_batch(headlines: list[NewsHeadline]) -> list[HeadlineScore]:
    if not headlines:
        return []
    out = SignificanceClassifier()(headlines=headlines)
    return out.scores
