"""Tests for the figure_deviation core data models.

These types underpin the generalised tone-deviation engine that supersedes the
fed-speech listener. See docs/plans/2026-05-08-figure-deviation-design.md.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


# ────────────────────────── FigurePost ───────────────────────────────────────


def test_figure_post_validates_source_enum():
    from castelino.triggers.figure_deviation.models import FigurePost

    post = FigurePost(
        figure_id="trump",
        text="China is dumping again",
        ts=datetime.now(UTC),
        source="x_api",
        event_id="tweet_12345",
    )
    assert post.source == "x_api"
    assert post.figure_id == "trump"
    assert post.event_id == "tweet_12345"
    # raw_meta defaults to empty dict
    assert post.raw_meta == {}
    # source_url is optional and defaults to None
    assert post.source_url is None


def test_figure_post_rejects_unknown_source():
    from castelino.triggers.figure_deviation.models import FigurePost

    with pytest.raises(ValidationError):
        FigurePost(
            figure_id="trump",
            text="x",
            ts=datetime.now(UTC),
            source="rss",  # not a valid source
            event_id="x",
        )


def test_figure_post_accepts_audio_source_for_speech_backcompat():
    from castelino.triggers.figure_deviation.models import FigurePost

    post = FigurePost(
        figure_id="powell",
        text="The committee remains data-dependent.",
        ts=datetime.now(UTC),
        source="audio",
        event_id="fomc-2026-05-08",
        source_url="https://federalreserve.gov/...",
        raw_meta={"venue": "FOMC press conference"},
    )
    assert post.source == "audio"
    assert post.raw_meta["venue"] == "FOMC press conference"


# ────────────────────────── FigureBaseline ───────────────────────────────────


def test_figure_baseline_requires_lexicon_version_match_field():
    from castelino.triggers.figure_deviation.models import FigureBaseline

    base = FigureBaseline(
        figure_id="trump",
        lexicon_name="trade_protectionist_v1",
        lexicon_version=1,
        mean=0.12,
        std=0.34,
        n_samples=480,
        last_refreshed=datetime.now(UTC),
    )
    assert base.lexicon_version == 1
    assert base.n_samples == 480


def test_figure_baseline_rejects_negative_std():
    from castelino.triggers.figure_deviation.models import FigureBaseline

    with pytest.raises(ValidationError):
        FigureBaseline(
            figure_id="trump",
            lexicon_name="trade_protectionist_v1",
            lexicon_version=1,
            mean=0.12,
            std=-0.1,  # invalid
            n_samples=10,
            last_refreshed=datetime.now(UTC),
        )


def test_figure_baseline_rejects_negative_n_samples():
    from castelino.triggers.figure_deviation.models import FigureBaseline

    with pytest.raises(ValidationError):
        FigureBaseline(
            figure_id="trump",
            lexicon_name="trade_protectionist_v1",
            lexicon_version=1,
            mean=0.12,
            std=0.2,
            n_samples=-5,
            last_refreshed=datetime.now(UTC),
        )


# ────────────────────────── LexiconScore ─────────────────────────────────────


def test_lexicon_score_carries_hits_for_audit():
    from castelino.triggers.figure_deviation.models import LexiconScore

    s = LexiconScore(value=0.8, hits={"tariff": 1, "China tariff": 1})
    assert s.value == 0.8
    assert sum(s.hits.values()) == 2
    # sub_axis_scores defaults to None for non-multi-axis lexicons
    assert s.sub_axis_scores is None


def test_lexicon_score_supports_sub_axes_for_regulatory():
    from castelino.triggers.figure_deviation.models import LexiconScore

    s = LexiconScore(
        value=0.4,
        hits={"bitcoin": 1, "drill": 1},
        sub_axis_scores={
            "crypto_friendly": 0.6,
            "oil_friendly": 0.5,
            "defence_hawkish": 0.0,
            "tech_hostile": 0.0,
        },
    )
    assert s.sub_axis_scores["crypto_friendly"] == 0.6
    assert s.sub_axis_scores["defence_hawkish"] == 0.0


def test_lexicon_score_value_clamped_to_unit_range():
    from castelino.triggers.figure_deviation.models import LexiconScore

    # values outside [-1, 1] should fail validation — scores are normalised
    with pytest.raises(ValidationError):
        LexiconScore(value=1.5, hits={})
    with pytest.raises(ValidationError):
        LexiconScore(value=-2.0, hits={})


# ────────────────────────── FigureDeviationTrigger ───────────────────────────


def test_figure_deviation_trigger_includes_directional_tags():
    from castelino.triggers.figure_deviation.models import FigureDeviationTrigger

    t = FigureDeviationTrigger(
        figure_id="trump",
        lexicon="trade_protectionist_v1",
        z=2.4,
        direction="positive",
        directional_tags=["usd_up", "em_equity_down"],
        decisive_phrase="50% tariffs starting Monday",
        confirmed_by_llm=True,
        confidence=0.82,
        window_post_ids=["tweet_1", "tweet_2", "tweet_3"],
    )
    assert "usd_up" in t.directional_tags
    assert t.confirmed_by_llm is True
    assert t.confidence == 0.82


def test_figure_deviation_trigger_rejects_invalid_direction():
    from castelino.triggers.figure_deviation.models import FigureDeviationTrigger

    with pytest.raises(ValidationError):
        FigureDeviationTrigger(
            figure_id="trump",
            lexicon="trade_protectionist_v1",
            z=2.4,
            direction="up",  # must be "positive" or "negative"
            directional_tags=[],
            decisive_phrase="x",
            confirmed_by_llm=True,
            confidence=0.5,
            window_post_ids=[],
        )


def test_figure_deviation_trigger_confidence_in_unit_range():
    from castelino.triggers.figure_deviation.models import FigureDeviationTrigger

    with pytest.raises(ValidationError):
        FigureDeviationTrigger(
            figure_id="trump",
            lexicon="x",
            z=2.0,
            direction="positive",
            directional_tags=[],
            decisive_phrase="x",
            confirmed_by_llm=True,
            confidence=1.5,  # invalid
            window_post_ids=[],
        )


def test_figure_deviation_trigger_serializable_to_dict():
    """The trigger must be cleanly serialisable so it persists into the
    approval queue audit trail."""
    from castelino.triggers.figure_deviation.models import FigureDeviationTrigger

    t = FigureDeviationTrigger(
        figure_id="trump",
        lexicon="trade_protectionist_v1",
        z=1.78,
        direction="positive",
        directional_tags=["usd_up"],
        decisive_phrase="x",
        confirmed_by_llm=True,
        confidence=0.82,
        window_post_ids=["a"],
    )
    payload = t.model_dump()
    assert payload["lexicon"] == "trade_protectionist_v1"
    assert payload["directional_tags"] == ["usd_up"]
