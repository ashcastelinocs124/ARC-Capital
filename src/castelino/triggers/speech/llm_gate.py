"""Stage B — LLM confirmation gate for tone shifts.

Only invoked when Stage A z-score crosses the threshold. Mirrors the pattern
of triggers/significance.score_batch — keeps LLM out of the hot path.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from castelino.agents.base import LLMClient
from castelino.triggers.speech.models import BaselineVector


class SpeechShiftClassification(BaseModel):
    is_shift: bool
    direction: Literal["hawkish", "dovish", "neutral"]
    magnitude: float = Field(ge=0.0, le=1.0)
    decisive_phrase: str
    rationale: str


SYSTEM = """\
You evaluate whether a Fed speaker has shifted tone meaningfully relative to
their own recent baseline. Be skeptical: only flag a shift if the phrasing
is materially different from how this person has been talking. A hawk being
hawkish is NOT a shift. A dove turning hawkish IS.
Return JSON only.
"""

USER = """\
Speaker: {full_name}
Their recent baseline tone: hawkish_dovish_mean={mean:+.2f}, std={std:.2f}
(negative = dovish, positive = hawkish)

The last few sentences they spoke:
\"\"\"{window}\"\"\"

Is this a meaningful tone shift relative to their baseline?
"""


def classify_speech_shift(
    *,
    client: LLMClient,
    full_name: str,
    baseline: BaselineVector,
    rolling_window_text: str,
    model: str = "gpt-4o-mini",
) -> SpeechShiftClassification:
    """Stage B confirmation gate — single structured-output LLM call.

    Returns a typed SpeechShiftClassification. Caller is responsible for
    deciding whether to act on `is_shift=True` (e.g. emit a trigger event).
    """
    return client.parse(
        model=model,
        system=SYSTEM,
        user=USER.format(
            full_name=full_name,
            mean=baseline.hawkish_dovish_mean,
            std=baseline.hawkish_dovish_std,
            window=rolling_window_text,
        ),
        schema=SpeechShiftClassification,
        max_tokens=400,
    )
