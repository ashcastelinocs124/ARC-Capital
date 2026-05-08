"""Persona builder + persistence."""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from castelino.config import get_settings
from castelino.triggers.speech.baseline import build_baseline
from castelino.triggers.speech.models import (
    BaselineVector, ScoredSpeech, SpeakerPersona,
)
from castelino.triggers.speech.scorer import (
    Lexicon, load_lexicon, score_speech, split_sentences,
)
from castelino.triggers.speech.scrapers.fed import ParsedSpeech


def _personas_dir(root: Path | None = None) -> Path:
    if root is not None:
        return root / "personas"
    return get_settings().resolved_paths.data / "personas"


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
    d = _personas_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{p.speaker_id}.json"
    path.write_text(p.model_dump_json(indent=2))
    return path


def load_persona(speaker_id: str, *, root: Path | None = None) -> SpeakerPersona:
    path = _personas_dir(root) / f"{speaker_id}.json"
    return SpeakerPersona.model_validate_json(path.read_text())
