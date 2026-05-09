"""Wave 6.5 — FigureProfile data model + store tests."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from castelino.triggers.figure_deviation.profile.models import (
    Chunk,
    FigureCard,
    FigureProfileMeta,
    RetrievedChunk,
)
from castelino.triggers.figure_deviation.profile.store import FigureProfileStore


# ────────────────────────── models ──────────────────────────────────────────


def test_figure_card_required_sections():
    card = FigureCard(
        figure_id="trump",
        version=1,
        belief_summary="Protectionist on trade; pressure-the-Fed on monetary",
        decision_framework="Negotiate from threats; follow through ~33% baseline",
        signature_phrases=["America First", "massive", "the best"],
        rhetorical_tells={
            "committed": ["starting Monday", "by next week"],
            "exploratory": ["looking at", "considering"],
        },
    )
    assert card.figure_id == "trump"
    assert "America First" in card.signature_phrases
    assert "starting Monday" in card.rhetorical_tells["committed"]


def test_retrieved_chunk_carries_provenance():
    c = RetrievedChunk(
        chunk_id="trump:tweet_outcome_examples.md:42",
        text="March 14 2018: 'tariffs starting Monday' tweet → 25% tariff Apr 3.",
        section="tweet_outcome_examples",
        similarity=0.81,
        source_doc="tweet_outcome_examples.md",
    )
    assert c.section == "tweet_outcome_examples"
    assert 0 <= c.similarity <= 1


# ────────────────────────── store ──────────────────────────────────────────


def test_store_upsert_and_query_round_trip(tmp_path):
    store = FigureProfileStore(figure_id="trump", base_dir=tmp_path)
    store.upsert_chunks([
        Chunk(id="t1", text="Trump tariff history follow-through 71% with named advisors",
              section="behavioural_patterns",
              source_doc="behavioural_patterns.md"),
        Chunk(id="t2", text="Drill baby drill — energy dominance speech",
              section="track_record_chronology",
              source_doc="track_record_chronology.md"),
    ])
    results = store.query(text="tariff follow-through", top_k=2)
    assert len(results) > 0
    # The behavioural_patterns chunk about tariff follow-through should rank
    # higher than the unrelated drilling chunk
    sections = [r.section for r in results]
    assert "behavioural_patterns" in sections


def test_store_filters_by_section(tmp_path):
    store = FigureProfileStore(figure_id="trump", base_dir=tmp_path)
    store.upsert_chunks([
        Chunk(id="a", text="x", section="behavioural_patterns",
              source_doc="b.md"),
        Chunk(id="b", text="y", section="tweet_outcome_examples",
              source_doc="t.md"),
        Chunk(id="c", text="z", section="rhetorical_tells",
              source_doc="r.md"),
    ])
    results = store.query(
        text="any query", top_k=10,
        section_filter=["tweet_outcome_examples", "track_record_chronology"],
    )
    sections = [r.section for r in results]
    assert all(s == "tweet_outcome_examples" for s in sections)


def test_store_versioning_persisted(tmp_path):
    store = FigureProfileStore(figure_id="trump", base_dir=tmp_path)
    store.set_version(2, source_manifest=["track_record_chronology.md"])
    meta = store.read_meta()
    assert meta is not None
    assert meta.version == 2
    assert "track_record_chronology.md" in meta.source_manifest


def test_store_is_built_returns_false_when_unpopulated(tmp_path):
    store = FigureProfileStore(figure_id="trump", base_dir=tmp_path)
    assert store.is_built() is False


def test_store_is_built_returns_true_after_full_build(tmp_path):
    store = FigureProfileStore(figure_id="trump", base_dir=tmp_path)
    store.upsert_chunks([Chunk(id="t1", text="x", section="bio", source_doc="b.md")])
    store.set_version(1, source_manifest=["b.md"])
    assert store.is_built() is True


def test_store_query_returns_empty_on_empty_index(tmp_path):
    store = FigureProfileStore(figure_id="trump", base_dir=tmp_path)
    assert store.query(text="anything") == []


def test_store_card_round_trip(tmp_path):
    store = FigureProfileStore(figure_id="trump", base_dir=tmp_path)
    card = FigureCard(
        figure_id="trump", version=1,
        belief_summary="x", decision_framework="y",
        signature_phrases=["America First"],
    )
    store.write_card(card)
    loaded = store.read_card()
    assert loaded is not None
    assert loaded.belief_summary == "x"
    assert "America First" in loaded.signature_phrases
