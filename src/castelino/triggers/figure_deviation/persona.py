"""Persona builder + persistence.

Wave 2 Task 2.3 — persona JSON files now live at
``data/personas/<figure_id>/<lexicon_name>.json`` instead of the legacy
``data/personas/<id>.json`` layout. The nested layout lets a single figure
hold multiple lexicon-keyed baselines side by side (Trump's three lexicons,
future ECB speakers' alternative lexicons, etc.).

`load_persona()` falls back to the legacy flat path with a `DeprecationWarning`
so existing on-disk files continue to work until the migration script
(`scripts/migrate_persona_layout.py`) runs.
"""
from __future__ import annotations

import warnings
from datetime import datetime, UTC
from pathlib import Path

from castelino.config import get_settings
from castelino.triggers.figure_deviation.baseline import build_baseline
from castelino.triggers.figure_deviation.speech_models import (
    BaselineVector, ScoredSpeech, SpeakerPersona,
)
from castelino.triggers.figure_deviation.scorer import (
    Lexicon, load_lexicon, score_speech, split_sentences,
)
from castelino.triggers.figure_deviation.scrapers.fed import ParsedSpeech


def _personas_dir(root: Path | None = None) -> Path:
    if root is not None:
        return root / "personas"
    return get_settings().resolved_paths.data / "personas"


def baseline_path(
    *, figure_id: str, lexicon_name: str, root: Path | None = None,
) -> Path:
    """Resolve the canonical path for a figure × lexicon baseline JSON file.

    Used by both `save_persona` and `load_persona`. Centralised so the
    migration script and any other tools agree on the layout.
    """
    return _personas_dir(root) / figure_id / f"{lexicon_name}.json"


def _legacy_persona_path(
    *, speaker_id: str, root: Path | None = None,
) -> Path:
    """The old flat path (`<root>/personas/<id>.json`). Used as a load-time
    fallback only; never written to."""
    return _personas_dir(root) / f"{speaker_id}.json"


def build_persona_from_speeches(
    *,
    speaker_id: str,
    full_name: str,
    role: str,
    speeches: list[ParsedSpeech],
    lexicon_version: str,
    baseline_window_days: int = 365,
    half_life_months: float = 6.0,
) -> SpeakerPersona:
    lex = load_lexicon(lexicon_version)
    scored: list[ScoredSpeech] = []
    for sp in speeches:
        sentences = split_sentences(sp.text)
        result = score_speech(sentences, lexicon=lex)
        scored.append(ScoredSpeech(
            speech_id=sp.url.rsplit("/", 1)[-1].replace(".htm", ""),
            date=sp.date, venue=sp.venue, score=result.score,
            n_policy_sentences=result.n_policy_sentences,
        ))
    bv = build_baseline(scored, half_life_months=half_life_months)
    return SpeakerPersona(
        speaker_id=speaker_id, full_name=full_name, role=role,
        baseline_window_days=baseline_window_days,
        last_updated=datetime.now(UTC),
        speeches_in_window=scored, baseline_vector=bv,
        lexicon_version=lexicon_version,
    )


def save_persona(p: SpeakerPersona, *, root: Path | None = None) -> Path:
    """Write the persona to its nested path. The lexicon_version on the
    persona itself determines which file in the figure's directory is
    written."""
    path = baseline_path(
        figure_id=p.speaker_id, lexicon_name=p.lexicon_version, root=root,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(p.model_dump_json(indent=2))
    return path


def load_persona(
    speaker_id: str,
    *,
    lexicon_name: str | None = None,
    root: Path | None = None,
) -> SpeakerPersona:
    """Load the persona from its nested path; fall back to the legacy flat
    path with a DeprecationWarning so pre-migration data still works.

    `lexicon_name` defaults to `cfg.speech.lexicon_version` when not given.
    Once Wave 5 wires the orchestrator to the new config, every caller will
    pass it explicitly and this default falls away.
    """
    if lexicon_name is None:
        lexicon_name = get_settings().speech.lexicon_version
    new_path = baseline_path(
        figure_id=speaker_id, lexicon_name=lexicon_name, root=root,
    )
    if new_path.exists():
        return SpeakerPersona.model_validate_json(new_path.read_text())
    legacy = _legacy_persona_path(speaker_id=speaker_id, root=root)
    if legacy.exists():
        warnings.warn(
            f"Loading persona from legacy flat layout at {legacy}. "
            f"Run `python scripts/migrate_persona_layout.py` to migrate to "
            f"the nested layout (data/personas/<id>/<lexicon>.json).",
            DeprecationWarning,
            stacklevel=2,
        )
        return SpeakerPersona.model_validate_json(legacy.read_text())
    raise FileNotFoundError(
        f"No persona for {speaker_id} × {lexicon_name} at {new_path} "
        f"(also checked legacy {legacy}).",
    )
