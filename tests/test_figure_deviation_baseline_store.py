"""Wave 3 Task 3.2 — per-lexicon BaselineStore.

The existing audio-rich `SpeakerPersona` files at `data/personas/...` are
unaffected. `BaselineStore` persists the generic `FigureBaseline` type at
`data/figure_baselines/<figure_id>/<lexicon_name>.json` for the orchestrator's
fast-path lookups, and is the canonical storage when a non-audio source
(X API, Sonar) feeds the engine in Wave 5+.

Critical safety: load() hard-fails with `LexiconVersionMismatch` if the
stored baseline's lexicon_version doesn't match the current lexicon YAML.
This prevents silently scoring against the wrong baseline after a lexicon
bump.
"""
from __future__ import annotations

import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from castelino.triggers.figure_deviation.models import FigureBaseline


# ────────────────────────── basic save / load round-trip ─────────────────────


def test_baseline_store_save_writes_nested_path(tmp_path):
    from castelino.triggers.figure_deviation.baseline_store import BaselineStore

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "trade_protectionist_v1.yaml").write_text(
        "name: trade_protectionist_v1\nversion: 1\n",
    )
    store = BaselineStore(base_dir=tmp_path / "baselines", lexicon_dir=lex_dir)
    base = FigureBaseline(
        figure_id="trump",
        lexicon_name="trade_protectionist_v1",
        lexicon_version=1,
        mean=0.12,
        std=0.18,
        n_samples=480,
        last_refreshed=datetime.now(UTC),
    )
    path = store.save(base)
    assert path == tmp_path / "baselines" / "trump" / "trade_protectionist_v1.json"
    assert path.exists()


def test_baseline_store_load_round_trip(tmp_path):
    from castelino.triggers.figure_deviation.baseline_store import BaselineStore

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "trade_protectionist_v1.yaml").write_text(
        "name: trade_protectionist_v1\nversion: 1\n",
    )
    store = BaselineStore(base_dir=tmp_path / "baselines", lexicon_dir=lex_dir)
    saved = FigureBaseline(
        figure_id="trump",
        lexicon_name="trade_protectionist_v1",
        lexicon_version=1,
        mean=0.12,
        std=0.18,
        n_samples=480,
        last_refreshed=datetime.now(UTC),
    )
    store.save(saved)
    loaded = store.load(figure_id="trump", lexicon_name="trade_protectionist_v1")
    assert loaded.figure_id == "trump"
    assert loaded.lexicon_name == "trade_protectionist_v1"
    assert loaded.mean == 0.12
    assert loaded.std == 0.18
    assert loaded.n_samples == 480


# ────────────────────────── isolation across (figure × lexicon) ─────────────


def test_baseline_store_isolated_per_lexicon(tmp_path):
    """Trump can have three independent baselines, one per lexicon, no
    cross-contamination."""
    from castelino.triggers.figure_deviation.baseline_store import BaselineStore

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    for name in ("trade_protectionist_v1", "fed_pressure_v1", "regulatory_stance_v1"):
        (lex_dir / f"{name}.yaml").write_text(f"name: {name}\nversion: 1\n")
    store = BaselineStore(base_dir=tmp_path / "baselines", lexicon_dir=lex_dir)
    for lex, mean in [
        ("trade_protectionist_v1", 0.5),
        ("fed_pressure_v1", 0.0),
        ("regulatory_stance_v1", 0.2),
    ]:
        store.save(FigureBaseline(
            figure_id="trump", lexicon_name=lex, lexicon_version=1,
            mean=mean, std=0.1, n_samples=100,
            last_refreshed=datetime.now(UTC),
        ))
    assert store.load(
        figure_id="trump", lexicon_name="trade_protectionist_v1",
    ).mean == 0.5
    assert store.load(
        figure_id="trump", lexicon_name="fed_pressure_v1",
    ).mean == 0.0
    assert store.load(
        figure_id="trump", lexicon_name="regulatory_stance_v1",
    ).mean == 0.2


def test_baseline_store_isolated_per_figure(tmp_path):
    """Powell's hawkish_dovish baseline is independent of any other figure's."""
    from castelino.triggers.figure_deviation.baseline_store import BaselineStore

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "hawkish_dovish_v1.yaml").write_text(
        "name: hawkish_dovish_v1\nversion: 1\n",
    )
    store = BaselineStore(base_dir=tmp_path / "baselines", lexicon_dir=lex_dir)
    for fid, mean in [("powell", 0.05), ("williams", -0.10), ("bullard", 0.30)]:
        store.save(FigureBaseline(
            figure_id=fid, lexicon_name="hawkish_dovish_v1", lexicon_version=1,
            mean=mean, std=0.15, n_samples=50,
            last_refreshed=datetime.now(UTC),
        ))
    assert store.load(
        figure_id="williams", lexicon_name="hawkish_dovish_v1",
    ).mean == -0.10


# ────────────────────────── version-mismatch hard-fail ──────────────────────


def test_baseline_store_load_hard_fails_on_version_mismatch(tmp_path):
    """If the stored baseline's lexicon_version != current lexicon YAML's
    version, load() must raise LexiconVersionMismatch with a helpful message.
    This is the load-bearing safety: silently scoring against a v1 baseline
    when the lexicon is now v2 would corrupt every z-score downstream."""
    from castelino.triggers.figure_deviation.baseline_store import (
        BaselineStore,
        LexiconVersionMismatch,
    )

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    # Lexicon YAML claims version 2
    (lex_dir / "trade_protectionist_v1.yaml").write_text(
        "name: trade_protectionist_v1\nversion: 2\n",
    )
    store = BaselineStore(base_dir=tmp_path / "baselines", lexicon_dir=lex_dir)
    # Save a baseline pinned to version 1 (older)
    store.save(FigureBaseline(
        figure_id="trump",
        lexicon_name="trade_protectionist_v1",
        lexicon_version=1,
        mean=0.12, std=0.18, n_samples=100,
        last_refreshed=datetime.now(UTC),
    ))
    with pytest.raises(LexiconVersionMismatch) as exc_info:
        store.load(figure_id="trump", lexicon_name="trade_protectionist_v1")
    msg = str(exc_info.value)
    assert "trump" in msg
    assert "trade_protectionist_v1" in msg
    # User must be told how to recover
    assert "figure-refresh" in msg or "refresh" in msg


def test_baseline_store_load_passes_when_version_matches(tmp_path):
    from castelino.triggers.figure_deviation.baseline_store import BaselineStore

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "trade_protectionist_v1.yaml").write_text(
        "name: trade_protectionist_v1\nversion: 3\n",
    )
    store = BaselineStore(base_dir=tmp_path / "baselines", lexicon_dir=lex_dir)
    store.save(FigureBaseline(
        figure_id="trump",
        lexicon_name="trade_protectionist_v1",
        lexicon_version=3,
        mean=0.12, std=0.18, n_samples=100,
        last_refreshed=datetime.now(UTC),
    ))
    loaded = store.load(figure_id="trump", lexicon_name="trade_protectionist_v1")
    assert loaded.lexicon_version == 3


def test_baseline_store_load_raises_filenotfound_when_baseline_missing(tmp_path):
    from castelino.triggers.figure_deviation.baseline_store import BaselineStore

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "trade_protectionist_v1.yaml").write_text(
        "name: trade_protectionist_v1\nversion: 1\n",
    )
    store = BaselineStore(base_dir=tmp_path / "baselines", lexicon_dir=lex_dir)
    with pytest.raises(FileNotFoundError, match="trump"):
        store.load(figure_id="trump", lexicon_name="trade_protectionist_v1")


def test_baseline_store_load_raises_when_lexicon_yaml_missing(tmp_path):
    """If the baseline exists but the lexicon YAML doesn't, that's a config
    error — the store cannot validate version, must fail loudly."""
    from castelino.triggers.figure_deviation.baseline_store import BaselineStore

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    store = BaselineStore(base_dir=tmp_path / "baselines", lexicon_dir=lex_dir)
    store.save(FigureBaseline(
        figure_id="trump", lexicon_name="ghost_v1", lexicon_version=1,
        mean=0.0, std=0.1, n_samples=10,
        last_refreshed=datetime.now(UTC),
    ))
    with pytest.raises(FileNotFoundError, match="ghost_v1"):
        store.load(figure_id="trump", lexicon_name="ghost_v1")
