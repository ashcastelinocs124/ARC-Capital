"""Helpers for wiring FigureProfile retrieval into the Hypothesis Agent.

Wave 7 Task 7.2 — orchestrator-side glue. Stays out of `agents/hypothesis.py`
to keep the agent decoupled from figure-deviation concerns; the agent just
takes a pre-formatted `figure_deviation_context` string.
"""
from __future__ import annotations

from castelino.triggers.figure_deviation.models import FigureDeviationTrigger
from castelino.triggers.figure_deviation.profile.models import RetrievedChunk
from castelino.triggers.figure_deviation.profile.store import FigureProfileStore


# Sections retrieved for hypothesis-time context — DIFFERENT from Stage B's
# (behavioural_patterns / rhetorical_tells). The two layers see complementary
# slices: Stage B gets bluster-vs-commitment context; the agent gets outcome
# examples + track record + cabinet for analogy reasoning.
HYPOTHESIS_SECTIONS = (
    "tweet_outcome_examples",
    "track_record_chronology",
    "current_cabinet",
    "biographical",
)


def build_figure_deviation_context(
    *,
    trigger: FigureDeviationTrigger,
    decisive_phrase: str,
    store: FigureProfileStore | None,
    top_k: int = 5,
) -> tuple[str, list[RetrievedChunk]]:
    """Compose the prompt block for the Hypothesis Agent's figure_deviation
    parameter, plus the list of retrieved chunks for the audit trail.

    `store` may be None (figure has no built profile yet) — the context block
    still includes the trigger's directional tags + decisive phrase so the
    agent has something to anchor on.
    """
    retrieved: list[RetrievedChunk] = []
    if store is not None and store.is_built():
        retrieved = store.query(
            text=decisive_phrase or "",
            top_k=top_k,
            section_filter=list(HYPOTHESIS_SECTIONS),
        )

    chunks_block = "\n".join(
        f"  • [{c.section}] {c.text[:280]}" for c in retrieved
    ) or "  (no profile chunks retrieved — figure has no built profile yet)"

    block = (
        f"Trigger: figure-deviation on {trigger.figure_id} × {trigger.lexicon}\n"
        f"  z-score: {trigger.z:+.2f}σ ({trigger.direction})\n"
        f"  decisive phrase: {trigger.decisive_phrase!r}\n"
        f"  directional tags (STRONG PRIOR): "
        f"{', '.join(trigger.directional_tags) or '(none)'}\n"
        f"  Stage B confirmed: {trigger.confirmed_by_llm} "
        f"(confidence {trigger.confidence:.2f})\n\n"
        f"Profile chunks (outcome examples + track record):\n{chunks_block}"
    )
    return block, retrieved
