"""Tests for FigureDeviationCfg in the central Settings.

The config schema is the contract by which `config.yaml` declares which
figures are tracked, on which sources, and against which lexicons. See
`docs/plans/2026-05-08-figure-deviation-design.md`.
"""
from __future__ import annotations

import pytest

from castelino.config import get_settings


def test_figure_deviation_section_exists_with_default_disabled_off():
    """The section must be present even before any figures are configured —
    Settings must not break for users who have not yet adopted the feature."""
    s = get_settings()
    assert hasattr(s, "figure_deviation")
    # `enabled` defaults to True so existing Fed speakers (once migrated) keep firing
    assert isinstance(s.figure_deviation.enabled, bool)


def test_figure_deviation_loads_with_powell_ported_to_new_schema():
    """Wave 1: only existing Fed speakers are ported. Trump comes in Wave 5."""
    s = get_settings()
    figure_ids = [f.id for f in s.figure_deviation.figures]
    assert "powell" in figure_ids


def test_figure_deviation_powell_uses_audio_source_and_hawkish_dovish_lexicon():
    s = get_settings()
    powell = next(f for f in s.figure_deviation.figures if f.id == "powell")
    assert any(src.type == "audio" for src in powell.sources)
    lexicon_names = [lex.name for lex in powell.lexicons]
    assert "hawkish_dovish_v1" in lexicon_names


def test_figure_deviation_lexicon_carries_directional_tags_and_threshold():
    s = get_settings()
    powell = next(f for f in s.figure_deviation.figures if f.id == "powell")
    hawk_lex = next(lex for lex in powell.lexicons if lex.name == "hawkish_dovish_v1")
    assert hawk_lex.threshold_sigma == 1.5
    assert hawk_lex.window_size == 5
    # Hawkish positive → rates_up, usd_up, gold_down (cardinal trade reaction)
    assert "rates_up" in hawk_lex.directional_tags_positive


def test_figure_deviation_baseline_has_sane_defaults():
    s = get_settings()
    powell = next(f for f in s.figure_deviation.figures if f.id == "powell")
    assert powell.baseline.window_days == 365
    assert powell.baseline.time_decay_half_life_days == 90
    assert powell.baseline.refresh_cadence_days == 7


def test_figure_deviation_source_supports_x_api_type():
    """Schema must accept x_api as a source type so Trump can be added in Wave 5
    without a schema change."""
    from castelino.config import TrackedFigureSourceCfg

    src = TrackedFigureSourceCfg(
        type="x_api",
        username="realdonaldtrump",
        poll_interval_min=5,
    )
    assert src.type == "x_api"
    assert src.username == "realdonaldtrump"


def test_figure_deviation_source_rejects_unknown_type():
    from castelino.config import TrackedFigureSourceCfg
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TrackedFigureSourceCfg(type="rss")


def test_figure_deviation_lexicon_supports_sub_axes_for_regulatory():
    """Schema must accept sub_axes for `regulatory_stance_v1` (crypto / oil / etc.)
    so we can add it as a lexicon for Trump in Wave 4 without a schema change."""
    from castelino.config import LexiconCfg

    lex = LexiconCfg(
        name="regulatory_stance_v1",
        threshold_sigma=2.0,
        window_size=5,
        sub_axes={
            "crypto_friendly": ["ibit_up"],
            "oil_friendly": ["xle_up"],
            "defence_hawkish": ["ita_up"],
            "tech_hostile": ["xlk_down"],
        },
    )
    assert lex.sub_axes is not None
    assert lex.sub_axes["crypto_friendly"] == ["ibit_up"]
