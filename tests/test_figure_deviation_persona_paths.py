"""Wave 2 Task 2.3 — verify nested persona JSON layout.

Old layout: data/personas/<speaker_id>.json (one file per speaker, single
lexicon implied from cfg.speech.lexicon_version).

New layout: data/personas/<figure_id>/<lexicon_name>.json (per-figure
directory, one file per lexicon, so Trump can have three baselines side by
side).

The old layout is supported as a read-time fallback with a deprecation
warning, so existing on-disk files keep working until the migration script
runs.
"""
from __future__ import annotations

import json
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pytest


# ────────────────────────── path resolution ─────────────────────────────────


def test_baseline_path_uses_nested_layout(tmp_path):
    from castelino.triggers.figure_deviation.persona import baseline_path

    p = baseline_path(
        figure_id="powell",
        lexicon_name="hawkish_dovish_v1",
        root=tmp_path,
    )
    assert p == tmp_path / "personas" / "powell" / "hawkish_dovish_v1.json"


def test_baseline_path_handles_lexicon_with_version_suffix(tmp_path):
    from castelino.triggers.figure_deviation.persona import baseline_path

    p = baseline_path(
        figure_id="trump",
        lexicon_name="trade_protectionist_v1",
        root=tmp_path,
    )
    assert p == tmp_path / "personas" / "trump" / "trade_protectionist_v1.json"


# ────────────────────────── round-trip: save then load ─────────────────────


def test_save_persona_writes_nested_path(tmp_path):
    from castelino.triggers.figure_deviation.persona import save_persona
    from castelino.triggers.figure_deviation.speech_models import (
        BaselineVector,
        SpeakerPersona,
    )

    persona = SpeakerPersona(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair, Federal Reserve",
        baseline_window_days=365,
        last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=BaselineVector(
            hawkish_dovish_mean=0.0,
            hawkish_dovish_std=0.1,
            hedging_density=0.05,
        ),
        lexicon_version="hawkish_dovish_v1",
    )
    path = save_persona(persona, root=tmp_path)
    assert path == tmp_path / "personas" / "powell" / "hawkish_dovish_v1.json"
    assert path.exists()
    # And the parent directory exists with that figure's name
    assert path.parent.name == "powell"


def test_load_persona_reads_nested_path(tmp_path):
    from castelino.triggers.figure_deviation.persona import (
        load_persona,
        save_persona,
    )
    from castelino.triggers.figure_deviation.speech_models import (
        BaselineVector,
        SpeakerPersona,
    )

    persona = SpeakerPersona(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair",
        baseline_window_days=365,
        last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=BaselineVector(
            hawkish_dovish_mean=0.12, hawkish_dovish_std=0.18,
            hedging_density=0.05,
        ),
        lexicon_version="hawkish_dovish_v1",
    )
    save_persona(persona, root=tmp_path)
    loaded = load_persona(
        speaker_id="powell", lexicon_name="hawkish_dovish_v1", root=tmp_path,
    )
    assert loaded.speaker_id == "powell"
    assert loaded.baseline_vector.hawkish_dovish_mean == 0.12


# ────────────────────────── back-compat: legacy flat layout ─────────────────


def test_load_persona_falls_back_to_legacy_flat_path_with_warning(tmp_path):
    """If the new nested path is missing but a legacy flat file exists,
    fall back so already-built personas keep working until migration."""
    from castelino.triggers.figure_deviation.persona import load_persona
    from castelino.triggers.figure_deviation.speech_models import (
        BaselineVector,
        SpeakerPersona,
    )

    persona = SpeakerPersona(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair",
        baseline_window_days=365,
        last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=BaselineVector(
            hawkish_dovish_mean=0.05, hawkish_dovish_std=0.2,
            hedging_density=0.05,
        ),
        lexicon_version="hawkish_dovish_v1",
    )
    # Write to the OLD flat path
    legacy_dir = tmp_path / "personas"
    legacy_dir.mkdir()
    legacy_path = legacy_dir / "powell.json"
    legacy_path.write_text(persona.model_dump_json(indent=2))
    # New nested path does NOT exist
    new_path = tmp_path / "personas" / "powell" / "hawkish_dovish_v1.json"
    assert not new_path.exists()
    # Loading should still work via fallback, with a DeprecationWarning
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = load_persona(
            speaker_id="powell",
            lexicon_name="hawkish_dovish_v1",
            root=tmp_path,
        )
    assert loaded.speaker_id == "powell"
    deprecation = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation) >= 1
    assert "migrate" in str(deprecation[0].message).lower() or \
           "legacy" in str(deprecation[0].message).lower()


def test_load_persona_raises_when_neither_path_exists(tmp_path):
    from castelino.triggers.figure_deviation.persona import load_persona

    with pytest.raises(FileNotFoundError):
        load_persona(
            speaker_id="powell",
            lexicon_name="hawkish_dovish_v1",
            root=tmp_path,
        )


# ────────────────────────── migration script ──────────────────────────────


def test_migration_script_relocates_legacy_files(tmp_path):
    """Running the migration moves data/personas/<id>.json to
    data/personas/<id>/<lexicon_name>.json based on the lexicon_version
    encoded in the persona JSON itself."""
    from scripts.migrate_persona_layout import migrate
    from castelino.triggers.figure_deviation.speech_models import (
        BaselineVector,
        SpeakerPersona,
    )

    legacy = tmp_path / "personas"
    legacy.mkdir()
    persona = SpeakerPersona(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair",
        baseline_window_days=365,
        last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=BaselineVector(
            hawkish_dovish_mean=0.05, hawkish_dovish_std=0.2,
            hedging_density=0.05,
        ),
        lexicon_version="hawkish_dovish_v1",
    )
    (legacy / "powell.json").write_text(persona.model_dump_json(indent=2))
    moved = migrate(personas_dir=legacy)
    assert (legacy / "powell" / "hawkish_dovish_v1.json").exists()
    assert not (legacy / "powell.json").exists()
    assert moved == 1


def test_migration_script_is_idempotent(tmp_path):
    """Running migration twice produces the same result and reports zero
    additional moves on the second run."""
    from scripts.migrate_persona_layout import migrate
    from castelino.triggers.figure_deviation.speech_models import (
        BaselineVector,
        SpeakerPersona,
    )

    legacy = tmp_path / "personas"
    legacy.mkdir()
    persona = SpeakerPersona(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair",
        baseline_window_days=365,
        last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=BaselineVector(
            hawkish_dovish_mean=0.05, hawkish_dovish_std=0.2,
            hedging_density=0.05,
        ),
        lexicon_version="hawkish_dovish_v1",
    )
    (legacy / "powell.json").write_text(persona.model_dump_json(indent=2))
    first = migrate(personas_dir=legacy)
    second = migrate(personas_dir=legacy)
    assert first == 1
    assert second == 0
    assert (legacy / "powell" / "hawkish_dovish_v1.json").exists()


def test_migration_script_reverse_flips_back(tmp_path):
    """--reverse flag flattens the nested layout back to legacy form for safe
    rollback if the migration introduces unexpected behaviour."""
    from scripts.migrate_persona_layout import migrate
    from castelino.triggers.figure_deviation.speech_models import (
        BaselineVector,
        SpeakerPersona,
    )

    legacy = tmp_path / "personas"
    legacy.mkdir()
    persona = SpeakerPersona(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair",
        baseline_window_days=365,
        last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=BaselineVector(
            hawkish_dovish_mean=0.05, hawkish_dovish_std=0.2,
            hedging_density=0.05,
        ),
        lexicon_version="hawkish_dovish_v1",
    )
    (legacy / "powell.json").write_text(persona.model_dump_json(indent=2))
    migrate(personas_dir=legacy)
    migrate(personas_dir=legacy, reverse=True)
    assert (legacy / "powell.json").exists()
    assert not (legacy / "powell" / "hawkish_dovish_v1.json").exists()
