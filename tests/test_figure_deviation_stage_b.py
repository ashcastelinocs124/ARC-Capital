"""Wave 7 Task 7.1 — Stage B + FigureProfile retrieval tests."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from castelino.triggers.figure_deviation.models import FigurePost
from castelino.triggers.figure_deviation.profile.models import (
    Chunk,
    FigureCard,
    RetrievedChunk,
)
from castelino.triggers.figure_deviation.profile.store import FigureProfileStore


# ────────────────────────── helpers ────────────────────────────────────────


class _FakeLLMClient:
    """Captures the prompt the Stage B call sent and returns a canned response."""

    def __init__(self, response_payload: dict) -> None:
        self.last_messages: list[dict] | None = None
        self._response = response_payload
        self.chat = SimpleNamespace(completions=SimpleNamespace(
            create=self._create,
        ))

    def _create(self, *, model, messages, **kwargs):
        self.last_messages = messages
        content = json.dumps(self._response)
        return SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=content)),
        ])


def _build_profile(tmp_path: Path, figure_id: str) -> FigureProfileStore:
    store = FigureProfileStore(figure_id=figure_id, base_dir=tmp_path)
    store.upsert_chunks([
        Chunk(id="c1",
              text="Trump tariff threats with named advisors follow through 71% (n=14)",
              section="behavioural_patterns",
              source_doc="behavioural_patterns.md"),
        Chunk(id="c2",
              text="'starting Monday' tells follow through 71%; 'considering' tells 18%",
              section="rhetorical_tells",
              source_doc="rhetorical_tells.md"),
        Chunk(id="c3",
              text="March 2025 tariff threat → 25% tariff EO April 2 (14-day delay)",
              section="tweet_outcome_examples",
              source_doc="tweet_outcome_examples.md"),
    ])
    store.write_card(FigureCard(
        figure_id=figure_id, version=1,
        belief_summary="Protectionist; pressure-the-Fed",
        decision_framework="Threats → 33% baseline follow-through; 71% with named advisors",
        signature_phrases=["America First", "massive", "the best"],
    ))
    store.set_version(1, source_manifest=["b.md", "r.md", "t.md"])
    return store


# ────────────────────────── tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_b_retrieves_and_includes_profile_chunks(tmp_path):
    from castelino.triggers.figure_deviation.stage_b import (
        ProfileAugmentedStageB,
    )
    _build_profile(tmp_path, "trump")
    client = _FakeLLMClient({
        "confirmed": True,
        "confidence": 0.84,
        "decisive_phrase": "50% tariffs starting Monday",
        "reasoning": "Named-advisor + specific date pattern matches 71% follow-through chunk",
    })
    gate = ProfileAugmentedStageB(
        client=client,
        profile_store_factory=lambda fid: FigureProfileStore(
            figure_id=fid, base_dir=tmp_path,
        ),
    )
    post = FigurePost(
        figure_id="trump",
        text="Massive 50% tariffs on Chinese steel starting Monday",
        ts=datetime.now(UTC),
        source="x_api",
        event_id="t1",
    )
    confirmed = await gate.confirm_deviation(
        figure_id="trump",
        lexicon="trade_protectionist_v1",
        post=post,
        z=2.4,
        window=[0.4, 0.6, 0.8],
    )
    assert confirmed is True
    # Prompt should contain at least one of the profile chunks
    user_msg = next(
        m for m in client.last_messages if m["role"] == "user"
    )["content"]
    assert "follow through 71%" in user_msg or "71%" in user_msg
    # Audit trail: last_confirmation populated with retrieved_chunks
    assert gate.last_confirmation is not None
    assert len(gate.last_confirmation.retrieved_chunks) > 0


@pytest.mark.asyncio
async def test_stage_b_filters_to_behavioural_sections_by_default(tmp_path):
    """Stage B should retrieve from behavioural_patterns / rhetorical_tells
    / current_cabinet — NOT outcome examples (those are Hypothesis Agent's slice)."""
    from castelino.triggers.figure_deviation.stage_b import (
        ProfileAugmentedStageB,
    )
    _build_profile(tmp_path, "trump")
    client = _FakeLLMClient({
        "confirmed": True, "confidence": 0.5,
        "decisive_phrase": "x", "reasoning": "y",
    })
    gate = ProfileAugmentedStageB(
        client=client,
        profile_store_factory=lambda fid: FigureProfileStore(
            figure_id=fid, base_dir=tmp_path,
        ),
    )
    post = FigurePost(
        figure_id="trump", text="anything",
        ts=datetime.now(UTC), source="x_api", event_id="t1",
    )
    await gate.confirm_deviation(
        figure_id="trump", lexicon="x", post=post, z=2.0, window=[0.5],
    )
    # All retrieved chunks must be from the default-filtered sections
    retrieved = gate.last_confirmation.retrieved_chunks
    assert all(
        r.section in ("behavioural_patterns", "rhetorical_tells", "current_cabinet")
        for r in retrieved
    )


@pytest.mark.asyncio
async def test_stage_b_vetoes_when_llm_says_not_confirmed(tmp_path):
    from castelino.triggers.figure_deviation.stage_b import (
        ProfileAugmentedStageB,
    )
    _build_profile(tmp_path, "trump")
    client = _FakeLLMClient({
        "confirmed": False, "confidence": 0.7,
        "decisive_phrase": "Biden's tariff",
        "reasoning": "Quoted criticism of opponent's tariff, not a Trump policy commitment",
    })
    gate = ProfileAugmentedStageB(
        client=client,
        profile_store_factory=lambda fid: FigureProfileStore(
            figure_id=fid, base_dir=tmp_path,
        ),
    )
    post = FigurePost(
        figure_id="trump", text="Biden's tariff was bad",
        ts=datetime.now(UTC), source="x_api", event_id="t1",
    )
    confirmed = await gate.confirm_deviation(
        figure_id="trump", lexicon="trade_protectionist_v1",
        post=post, z=1.6, window=[0.4, 0.5, 0.6],
    )
    assert confirmed is False
    assert "Biden" in gate.last_confirmation.decisive_phrase


@pytest.mark.asyncio
async def test_stage_b_defaults_to_veto_on_llm_error(tmp_path):
    """If the LLM call raises, Stage B must veto rather than emit on a
    crashed call — failing closed is the safe default for trade signals."""
    from castelino.triggers.figure_deviation.stage_b import (
        ProfileAugmentedStageB,
    )
    _build_profile(tmp_path, "trump")

    class ExplodingClient:
        chat = SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        ))

    gate = ProfileAugmentedStageB(
        client=ExplodingClient(),
        profile_store_factory=lambda fid: FigureProfileStore(
            figure_id=fid, base_dir=tmp_path,
        ),
    )
    post = FigurePost(
        figure_id="trump", text="x",
        ts=datetime.now(UTC), source="x_api", event_id="t1",
    )
    confirmed = await gate.confirm_deviation(
        figure_id="trump", lexicon="x", post=post, z=2.0, window=[0.5],
    )
    assert confirmed is False
    assert "fail" in gate.last_confirmation.reasoning.lower()


@pytest.mark.asyncio
async def test_stage_b_works_when_profile_not_built(tmp_path):
    """If a figure has no built profile yet, Stage B falls back to baseline-
    only context — confirmed=False shouldn't be the only safe path."""
    from castelino.triggers.figure_deviation.stage_b import (
        ProfileAugmentedStageB,
    )
    # Store exists but is empty (no chunks, no card)
    client = _FakeLLMClient({
        "confirmed": True, "confidence": 0.5,
        "decisive_phrase": "x", "reasoning": "no profile but pattern clear",
    })
    gate = ProfileAugmentedStageB(
        client=client,
        profile_store_factory=lambda fid: FigureProfileStore(
            figure_id=fid, base_dir=tmp_path,
        ),
    )
    post = FigurePost(
        figure_id="newcomer", text="anything",
        ts=datetime.now(UTC), source="x_api", event_id="t1",
    )
    confirmed = await gate.confirm_deviation(
        figure_id="newcomer", lexicon="x", post=post, z=2.0, window=[0.5],
    )
    assert confirmed is True
    # No chunks retrieved — but the call still went through
    assert gate.last_confirmation.retrieved_chunks == []
