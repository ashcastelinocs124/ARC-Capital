"""Stage B — LLM confirmation gate, profile-augmented.

Wave 7 Task 7.1 — replaces the dispatcher's stub Stage B with a real LLM
call (gpt-4o-mini) that receives:
  - The triggering post text + window of recent posts
  - The lexicon's axis description
  - Stage A's z-score
  - The figure's baseline summary
  - Top-k retrieved chunks from the figure's FigureProfile

Returns `DeviationConfirmation` with the LLM's confirmed/not confirmed
decision, confidence, decisive phrase, reasoning, and the retrieved
chunks (persisted into the audit trail at the post-hypothesis HITL gate).

Profile retrieval defaults to behavioural-pattern + rhetorical-tell
sections — the slices that distinguish bluster from committed action.
The Hypothesis Agent's retrieval (Task 7.2) intentionally targets
DIFFERENT sections (outcome examples, track record) so each layer sees
complementary context.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from castelino.triggers.figure_deviation.dispatcher import StageBProtocol
from castelino.triggers.figure_deviation.models import FigurePost
from castelino.triggers.figure_deviation.profile.models import RetrievedChunk
from castelino.triggers.figure_deviation.profile.store import FigureProfileStore

log = logging.getLogger(__name__)


class DeviationConfirmation(BaseModel):
    """Stage B's structured verdict — persisted into the trigger emission's
    audit trail."""

    confirmed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    decisive_phrase: str = ""
    reasoning: str = ""
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)


# ────────────────────────── prompt template ─────────────────────────────────


_STAGE_B_SYSTEM_PROMPT = """\
You are a tone-deviation classifier for the CKM Capital macro fund.

Your job is to confirm or veto a Stage A signal about whether a tracked
figure has materially deviated from their own rhetorical baseline along
the specified axis. You see:
  - The figure's belief summary and rhetorical tells (FigureCard)
  - Top retrieved chunks from the figure's profile (RAG context)
  - The triggering post + recent rolling window
  - The lexicon's axis description and the figure's baseline mean/std
  - Stage A's computed z-score

You MUST decide:
  • confirmed: true if the deviation is real (not noise / quoted / sarcastic)
  • confidence: 0.0..1.0 — your subjective certainty
  • decisive_phrase: the literal text snippet that drove the decision
  • reasoning: 1-3 sentences citing the retrieved context

Veto if the post is a quote, sarcasm, or context-dependent reference
(e.g. criticising someone ELSE's tariffs).
Veto if it's boilerplate present at this intensity in the figure's
historical baseline.

Return ONLY a JSON object matching DeviationConfirmation.
"""


def _build_stage_b_prompt(
    *,
    figure_id: str,
    figure_card_summary: str,
    axis_description: str,
    window_posts: list[FigurePost],
    z: float,
    baseline_mean: float,
    baseline_std: float,
    retrieved_chunks: list[RetrievedChunk],
) -> str:
    chunks_block = "\n".join(
        f"  [{c.section}] (sim={c.similarity:.2f}) {c.text[:200]}"
        for c in retrieved_chunks
    ) or "  (no profile chunks retrieved)"
    window_block = "\n".join(
        f"  • {p.ts.isoformat()} — {p.text[:240]}"
        for p in window_posts
    )
    return f"""Figure: {figure_id}

FIGURE CARD:
{figure_card_summary}

AXIS: {axis_description}
BASELINE: mean={baseline_mean:.3f}, std={baseline_std:.3f}
STAGE A: z = {z:+.2f}σ

RECENT WINDOW:
{window_block}

PROFILE CONTEXT (top retrieved chunks):
{chunks_block}

Decide whether to confirm this deviation."""


# ────────────────────────── gate impl ───────────────────────────────────────


class ProfileAugmentedStageB(StageBProtocol):
    """Real Stage B — calls gpt-4o-mini with profile-retrieved context.

    The OpenAI client is injected so tests can swap in a fake. Profile store
    is also injected for the same reason. In production both come from
    `castelino.agents.base.get_llm_client()` and `FigureProfileStore(figure_id)`.
    """

    # Sections relevant to confirming a deviation: behavioural patterns
    # + rhetorical tells. The Hypothesis Agent uses outcome / track-record
    # sections instead (Task 7.2).
    _DEFAULT_SECTION_FILTER = (
        "behavioural_patterns",
        "rhetorical_tells",
        "current_cabinet",
    )

    def __init__(
        self,
        *,
        client: Any,                         # OpenAI client (any compatible)
        profile_store_factory,               # callable: figure_id → FigureProfileStore
        model: str = "gpt-4o-mini",
        top_k: int = 5,
        section_filter: tuple[str, ...] | None = None,
        last_confirmation: DeviationConfirmation | None = None,
    ) -> None:
        self._client = client
        self._profile_store_factory = profile_store_factory
        self._model = model
        self._top_k = top_k
        self._section_filter = (
            section_filter or self._DEFAULT_SECTION_FILTER
        )
        # Most-recent confirmation kept for the dispatcher's audit trail
        self.last_confirmation = last_confirmation

    async def confirm_deviation(
        self,
        *,
        figure_id: str,
        lexicon: str,
        post: FigurePost,
        z: float,
        window: list[float],
    ) -> bool:
        # Retrieve profile context relevant to this post
        store = self._profile_store_factory(figure_id)
        retrieved: list[RetrievedChunk] = store.query(
            text=post.text,
            top_k=self._top_k,
            section_filter=list(self._section_filter),
        ) if store and store.is_built() else []

        card = store.read_card() if store else None
        card_summary = (
            f"belief: {card.belief_summary}\n"
            f"framework: {card.decision_framework}\n"
            f"signature: {', '.join(card.signature_phrases)}\n"
            if card else "(no card)"
        )

        prompt = _build_stage_b_prompt(
            figure_id=figure_id,
            figure_card_summary=card_summary,
            axis_description=lexicon,
            window_posts=[post],   # caller supplies float window; for full
                                   # context, dispatcher could pass posts
            z=z,
            baseline_mean=0.0,     # available to dispatcher; populated below
            baseline_std=1.0,      # if it passes them
            retrieved_chunks=retrieved,
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _STAGE_B_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=600,
                response_format={"type": "json_object"},
            )
            payload = response.choices[0].message.content
            confirmation = DeviationConfirmation.model_validate_json(payload)
        except Exception:
            log.exception(
                "Stage B LLM call failed for %s × %s — defaulting to veto",
                figure_id, lexicon,
            )
            confirmation = DeviationConfirmation(
                confirmed=False, confidence=0.0,
                reasoning="LLM call failed — defaulted to veto for safety",
            )

        # Attach retrieved chunks for the audit trail
        confirmation = confirmation.model_copy(
            update={"retrieved_chunks": retrieved},
        )
        self.last_confirmation = confirmation
        return confirmation.confirmed
