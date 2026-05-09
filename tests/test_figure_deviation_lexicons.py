"""Wave 4 — smoke tests for the three new Trump lexicons.

Each lexicon scores known examples in the expected direction. These are
not exhaustive; they pin down the gross behaviour so future tweaks don't
silently flip a sign.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from castelino.triggers.figure_deviation.scorer import Scorer

LEX_DIR = Path("data/lexicons")


@pytest.fixture
def scorer():
    return Scorer(lexicon_dir=LEX_DIR)


# ────────────────────────── trade_protectionist_v1 ───────────────────────────


def test_trade_protectionist_lexicon_loads(scorer):
    s = scorer.score_post(text="hello", lexicon_name="trade_protectionist_v1")
    assert s.value == 0.0  # no terms hit


def test_trade_protectionist_high_protectionist_post_scores_positive(scorer):
    s = scorer.score_post(
        text="Massive tariffs on China to level the playing field — America First!",
        lexicon_name="trade_protectionist_v1",
    )
    assert s.value > 0.5


def test_trade_protectionist_free_trade_post_scores_negative(scorer):
    s = scorer.score_post(
        text="We had a great meeting and signed a free trade partnership.",
        lexicon_name="trade_protectionist_v1",
    )
    assert s.value < -0.4


def test_trade_protectionist_neutral_post_scores_near_zero(scorer):
    s = scorer.score_post(
        text="Beautiful day in Florida, playing golf at Mar-a-Lago.",
        lexicon_name="trade_protectionist_v1",
    )
    assert -0.2 < s.value < 0.2


def test_trade_protectionist_has_at_least_30_terms(scorer):
    """Acceptance criterion 9 — minimum signal density."""
    lex = scorer._load("trade_protectionist_v1")
    assert len(lex.weighted_terms) >= 30


# ────────────────────────── fed_pressure_v1 ─────────────────────────────────


def test_fed_pressure_lexicon_loads(scorer):
    s = scorer.score_post(text="hello", lexicon_name="fed_pressure_v1")
    assert s.value == 0.0


def test_fed_pressure_attacking_powell_scores_positive(scorer):
    s = scorer.score_post(
        text="Powell should cut rates immediately. Fed is too late and asleep at the wheel.",
        lexicon_name="fed_pressure_v1",
    )
    assert s.value > 0.5


def test_fed_pressure_pro_independence_scores_negative(scorer):
    s = scorer.score_post(
        text="The Fed is data-dependent, respect the Fed and its mandate. Fed independence matters.",
        lexicon_name="fed_pressure_v1",
    )
    assert s.value < -0.4


def test_fed_pressure_at_least_25_terms(scorer):
    lex = scorer._load("fed_pressure_v1")
    assert len(lex.weighted_terms) >= 25


# ────────────────────────── regulatory_stance_v1 (multi-axis) ───────────────


def test_regulatory_lexicon_loads_with_sub_axes(scorer):
    s = scorer.score_post(text="hello", lexicon_name="regulatory_stance_v1")
    assert s.sub_axis_scores is not None
    assert "crypto_friendly" in s.sub_axis_scores
    assert "oil_friendly" in s.sub_axis_scores
    assert "defence_hawkish" in s.sub_axis_scores
    assert "tech_hostile" in s.sub_axis_scores


def test_regulatory_crypto_post_scores_only_crypto_axis(scorer):
    s = scorer.score_post(
        text="Bitcoin is the future. End Operation Chokepoint and debanking.",
        lexicon_name="regulatory_stance_v1",
    )
    assert s.sub_axis_scores["crypto_friendly"] > 0.5
    assert s.sub_axis_scores["oil_friendly"] < 0.2
    assert s.sub_axis_scores["defence_hawkish"] < 0.2
    assert s.sub_axis_scores["tech_hostile"] < 0.2


def test_regulatory_oil_post_scores_only_oil_axis(scorer):
    s = scorer.score_post(
        text="Drill baby drill. Energy dominance. Approve the Keystone pipeline.",
        lexicon_name="regulatory_stance_v1",
    )
    assert s.sub_axis_scores["oil_friendly"] > 0.5
    assert s.sub_axis_scores["crypto_friendly"] < 0.2


def test_regulatory_defence_post_scores_only_defence_axis(scorer):
    s = scorer.score_post(
        text="Peace through strength. Rebuild the military. Stand up to Iran and China military.",
        lexicon_name="regulatory_stance_v1",
    )
    assert s.sub_axis_scores["defence_hawkish"] > 0.4


def test_regulatory_tech_post_scores_only_tech_axis(scorer):
    s = scorer.score_post(
        text="Big tech censorship must end. Section 230 must be repealed. Stop the shadowban.",
        lexicon_name="regulatory_stance_v1",
    )
    assert s.sub_axis_scores["tech_hostile"] > 0.5


def test_regulatory_combined_post_scores_multiple_axes(scorer):
    """A tweet hitting two sectors should light up both sub-axes
    independently — the framework's whole point."""
    s = scorer.score_post(
        text="Bitcoin reserve. Drill baby drill. End the Green New Deal.",
        lexicon_name="regulatory_stance_v1",
    )
    assert s.sub_axis_scores["crypto_friendly"] > 0
    assert s.sub_axis_scores["oil_friendly"] > 0
    assert s.sub_axis_scores["tech_hostile"] == 0
