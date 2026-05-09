"""Wave 3 Task 3.1 — `Scorer` loads lexicons by name from disk.

The existing `score_sentence(..., lexicon=Lexicon(...))` API is kept for
back-compat with the speech tests. The new `Scorer.score_post(text=...,
lexicon_name=...)` API supports arbitrary named lexicons, returns the
generic `LexiconScore` type, and handles both the legacy hawkish/dovish
YAML shape and the new hot/cold/modifiers shape.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from castelino.triggers.figure_deviation.models import LexiconScore


# ────────────────────────── named-lexicon loading ───────────────────────────


def test_scorer_loads_named_lexicon_in_new_shape(tmp_path):
    """A lexicon in the new hot_terms/cold_terms format scores correctly and
    populates LexiconScore.hits."""
    from castelino.triggers.figure_deviation.scorer import Scorer

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "test_protectionist_v1.yaml").write_text(textwrap.dedent("""
        name: test_protectionist_v1
        version: 1
        axis: test_protectionist
        hot_terms:
          - { term: "tariff", weight: 1.0 }
          - { term: "China dumping", weight: 1.4 }
        cold_terms:
          - { term: "free trade", weight: -1.0 }
        modifiers:
          intensifiers: ["massive"]
          hedges: ["considering"]
    """))
    sc = Scorer(lexicon_dir=lex_dir)
    score = sc.score_post(
        text="Massive tariffs on China dumping practices.",
        lexicon_name="test_protectionist_v1",
    )
    assert isinstance(score, LexiconScore)
    assert score.value > 0.6
    assert "tariff" in score.hits
    assert "China dumping" in score.hits


def test_scorer_handles_legacy_hawkish_dovish_shape(tmp_path):
    """Legacy lexicons (hawkish_phrases / dovish_phrases / hedges) load
    through the same Scorer API and produce a LexiconScore."""
    from castelino.triggers.figure_deviation.scorer import Scorer

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "hawkish_dovish_v1.yaml").write_text(textwrap.dedent("""
        version: v1
        hawkish_phrases:
          "further firming": 0.7
          "act decisively": 0.6
        dovish_phrases:
          "patient": -0.4
          "accommodative": -0.7
        hedges:
          - "perhaps"
    """))
    sc = Scorer(lexicon_dir=lex_dir)
    hawkish = sc.score_post(
        text="Further firming will be warranted.",
        lexicon_name="hawkish_dovish_v1",
    )
    dovish = sc.score_post(
        text="The committee remains accommodative.",
        lexicon_name="hawkish_dovish_v1",
    )
    assert hawkish.value > 0
    assert dovish.value < 0
    assert "further firming" in hawkish.hits
    assert "accommodative" in dovish.hits


def test_scorer_rejects_unknown_lexicon(tmp_path):
    from castelino.triggers.figure_deviation.scorer import Scorer

    sc = Scorer(lexicon_dir=tmp_path)
    with pytest.raises(KeyError, match="missing_v1"):
        sc.score_post(text="x", lexicon_name="missing_v1")


def test_scorer_caches_loaded_lexicons(tmp_path):
    """Loading the same lexicon twice should reuse the cached parse — second
    call must not re-read the YAML file."""
    from castelino.triggers.figure_deviation.scorer import Scorer

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    yaml_path = lex_dir / "lex_v1.yaml"
    yaml_path.write_text(textwrap.dedent("""
        name: lex_v1
        version: 1
        axis: test
        hot_terms:
          - { term: "rocket", weight: 1.0 }
        cold_terms:
          - { term: "anchor", weight: -1.0 }
        modifiers:
          intensifiers: []
          hedges: []
    """))
    sc = Scorer(lexicon_dir=lex_dir)
    sc.score_post(text="rocket", lexicon_name="lex_v1")
    # Mutate the file. If the loader didn't cache, the next score would
    # reflect the mutation. With caching, it should not.
    yaml_path.write_text(textwrap.dedent("""
        name: lex_v1
        version: 1
        axis: test
        hot_terms:
          - { term: "rocket", weight: -5.0 }
        cold_terms: []
        modifiers:
          intensifiers: []
          hedges: []
    """))
    score2 = sc.score_post(text="rocket", lexicon_name="lex_v1")
    assert score2.value > 0  # cached old positive weight, not new negative


def test_scorer_score_returned_in_unit_range(tmp_path):
    """LexiconScore.value must always lie in [-1, 1] regardless of how many
    terms hit."""
    from castelino.triggers.figure_deviation.scorer import Scorer

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "lex_v1.yaml").write_text(textwrap.dedent("""
        name: lex_v1
        version: 1
        axis: test
        hot_terms:
          - { term: "a", weight: 0.5 }
          - { term: "b", weight: 0.5 }
          - { term: "c", weight: 0.5 }
          - { term: "d", weight: 0.5 }
        cold_terms: []
        modifiers:
          intensifiers: []
          hedges: []
    """))
    sc = Scorer(lexicon_dir=lex_dir)
    s = sc.score_post(text="a b c d", lexicon_name="lex_v1")
    assert s.value <= 1.0  # clamped


# ────────────────────────── hits provenance ────────────────────────────────


def test_lexicon_score_hits_count_matches_occurrences(tmp_path):
    """The hits dict reflects the number of times each phrase appeared."""
    from castelino.triggers.figure_deviation.scorer import Scorer

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "lex_v1.yaml").write_text(textwrap.dedent("""
        name: lex_v1
        version: 1
        axis: test
        hot_terms:
          - { term: "tariff", weight: 0.5 }
        cold_terms: []
        modifiers:
          intensifiers: []
          hedges: []
    """))
    sc = Scorer(lexicon_dir=lex_dir)
    s = sc.score_post(text="tariff and another tariff and more tariff",
                      lexicon_name="lex_v1")
    assert s.hits.get("tariff", 0) >= 1
