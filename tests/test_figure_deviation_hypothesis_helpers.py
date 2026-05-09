"""Wave 7 Task 7.2 — Hypothesis Agent FigureProfile helper tests."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from castelino.triggers.figure_deviation.models import FigureDeviationTrigger
from castelino.triggers.figure_deviation.profile.hypothesis_helpers import (
    HYPOTHESIS_SECTIONS,
    build_figure_deviation_context,
)
from castelino.triggers.figure_deviation.profile.models import (
    Chunk,
    FigureCard,
)
from castelino.triggers.figure_deviation.profile.store import FigureProfileStore


def _trigger() -> FigureDeviationTrigger:
    return FigureDeviationTrigger(
        figure_id="trump",
        lexicon="trade_protectionist_v1",
        z=2.4,
        direction="positive",
        directional_tags=["usd_up", "em_equity_down", "semis_down"],
        decisive_phrase="50% tariffs on Chinese steel starting Monday",
        confirmed_by_llm=True,
        confidence=0.84,
        window_post_ids=["t1", "t2", "t3"],
    )


def _build_profile(tmp_path: Path) -> FigureProfileStore:
    store = FigureProfileStore(figure_id="trump", base_dir=tmp_path)
    store.upsert_chunks([
        Chunk(id="o1",
              text="March 2025: 'massive tariffs on Chinese steel' tweet → "
                   "25% tariff EO Apr 2 (14-day delay). SPY -3.2% / 5d.",
              section="tweet_outcome_examples",
              source_doc="tweet_outcome_examples.md"),
        Chunk(id="o2",
              text="April 2024 tariff threat NOT followed through; Bessent "
                   "softened on CNBC within 48h.",
              section="tweet_outcome_examples",
              source_doc="tweet_outcome_examples.md"),
        Chunk(id="b1",
              text="Trump tariff threats with named advisors → 71% follow-through",
              section="behavioural_patterns",
              source_doc="behavioural_patterns.md"),
    ])
    store.set_version(1, source_manifest=["t.md", "b.md"])
    return store


def test_helper_retrieves_outcome_focused_sections(tmp_path):
    """Hypothesis Agent gets OUTCOME / TRACK-RECORD context — NOT
    behavioural_patterns (that's Stage B's slice)."""
    store = _build_profile(tmp_path)
    block, retrieved = build_figure_deviation_context(
        trigger=_trigger(),
        decisive_phrase="50% tariffs on Chinese steel starting Monday",
        store=store,
    )
    # All retrieved chunks must be in HYPOTHESIS_SECTIONS
    assert all(c.section in HYPOTHESIS_SECTIONS for c in retrieved)
    # Specifically: behavioural_patterns must NOT appear here
    assert all(c.section != "behavioural_patterns" for c in retrieved)


def test_helper_includes_directional_tags_in_prompt_block(tmp_path):
    store = _build_profile(tmp_path)
    block, _ = build_figure_deviation_context(
        trigger=_trigger(),
        decisive_phrase="x",
        store=store,
    )
    assert "usd_up" in block
    assert "em_equity_down" in block
    assert "semis_down" in block
    assert "STRONG PRIOR" in block


def test_helper_includes_decisive_phrase_in_prompt_block(tmp_path):
    store = _build_profile(tmp_path)
    block, _ = build_figure_deviation_context(
        trigger=_trigger(),
        decisive_phrase="50% tariffs on Chinese steel starting Monday",
        store=store,
    )
    assert "50% tariffs" in block


def test_helper_includes_outcome_chunks_in_prompt_block(tmp_path):
    """The retrieved outcome examples must literally appear in the block
    so the LLM has them as analogy basis."""
    store = _build_profile(tmp_path)
    block, retrieved = build_figure_deviation_context(
        trigger=_trigger(),
        decisive_phrase="50% tariffs on Chinese steel starting Monday",
        store=store,
    )
    assert len(retrieved) > 0
    assert "March 2025" in block or "April 2024" in block


def test_helper_handles_unbuilt_profile_gracefully(tmp_path):
    """A figure without a built profile still gets a usable context block
    — just the trigger payload, no retrieved chunks."""
    block, retrieved = build_figure_deviation_context(
        trigger=_trigger(),
        decisive_phrase="x",
        store=None,
    )
    assert retrieved == []
    assert "no profile chunks retrieved" in block
    assert "usd_up" in block  # directional tags still there


def test_hypothesis_agent_user_prompt_accepts_figure_deviation_context():
    """The agent's user_prompt method takes the context block as kwarg
    without breaking existing call sites that pass only world_state."""
    from castelino.agents.hypothesis import HypothesisAgent
    from castelino.memory.schemas import WorldStateBrief

    agent = HypothesisAgent()
    ws = WorldStateBrief(
        parent_trigger_id="trg-test",
        headlines=["Test headline"],
        summary="Test summary",
    )
    # Original call path — unchanged
    p_old = agent.user_prompt(world_state=ws, macro_context="")
    # New call path — figure_deviation_context is additive
    p_new = agent.user_prompt(
        world_state=ws,
        macro_context="",
        figure_deviation_context=(
            "Trigger: figure-deviation on trump × trade_protectionist_v1\n"
            "directional tags: usd_up, em_equity_down"
        ),
    )
    assert "FIGURE DEVIATION CONTEXT" not in p_old
    assert "FIGURE DEVIATION CONTEXT" in p_new
    assert "usd_up" in p_new
