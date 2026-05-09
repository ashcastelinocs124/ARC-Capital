"""Sentence-level scorer (legacy hawkish/dovish API + multi-lexicon Scorer).

The scoring function is the load-bearing invariant: identical scoring is used
for both the offline persona baseline and the live listener, so z-score
deviations compare like-for-like. If the lexicon changes, version it (v2,
v3, ...) and rebuild every persona from the historical corpus.

Wave 3 Task 3.1 added the `Scorer` class which loads lexicons from disk by
name and returns the generic `LexiconScore` model. It supports both the
legacy hawkish/dovish YAML shape and the new hot/cold/modifiers shape so a
single Scorer can drive every figure × lexicon combination uniformly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from castelino.triggers.figure_deviation.models import LexiconScore


@dataclass(frozen=True)
class Lexicon:
    version: str
    hawkish_phrases: dict[str, float]
    dovish_phrases: dict[str, float]
    hedges: tuple[str, ...]


def load_lexicon(version: str = "hawkish_dovish_v1") -> Lexicon:
    path = Path("data/lexicons") / f"{version}.yaml"
    raw = yaml.safe_load(path.read_text())
    return Lexicon(
        version=raw["version"],
        hawkish_phrases=dict(raw["hawkish_phrases"]),
        dovish_phrases=dict(raw["dovish_phrases"]),
        hedges=tuple(raw["hedges"]),
    )


# ────────────────────────── multi-lexicon Scorer ────────────────────────────


@dataclass(frozen=True)
class _NormalisedLexicon:
    """Internal uniform representation of any lexicon, regardless of the
    on-disk shape it came in. Both the legacy hawkish/dovish format and the
    new hot/cold/modifiers format are converted to this on load.

    `term_sub_axes` is populated only for multi-axis lexicons (e.g.
    regulatory_stance_v1) — maps term → which sub-axis owns it. Single-axis
    lexicons leave this empty.
    """

    name: str
    weighted_terms: dict[str, float]    # term → signed weight
    term_sub_axes: dict[str, str]       # term → sub_axis label (multi-axis only)
    sub_axes: tuple[str, ...]           # ordered sub-axis labels
    intensifiers: tuple[str, ...]
    hedges: tuple[str, ...]


def _normalise_lexicon_yaml(raw: dict, *, fallback_name: str) -> _NormalisedLexicon:
    """Coerce either YAML shape into the uniform internal representation."""
    name = raw.get("name", fallback_name)

    # Branch by shape: presence of hot_terms / cold_terms = new shape.
    if "hot_terms" in raw or "cold_terms" in raw:
        weighted: dict[str, float] = {}
        term_sub_axes: dict[str, str] = {}
        for entry in raw.get("hot_terms", []) or []:
            weighted[entry["term"]] = float(entry["weight"])
            if "sub_axis" in entry:
                term_sub_axes[entry["term"]] = entry["sub_axis"]
        for entry in raw.get("cold_terms", []) or []:
            weighted[entry["term"]] = float(entry["weight"])  # already negative
            if "sub_axis" in entry:
                term_sub_axes[entry["term"]] = entry["sub_axis"]
        modifiers = raw.get("modifiers") or {}
        intensifiers = tuple(modifiers.get("intensifiers", []) or [])
        hedges = tuple(modifiers.get("hedges", []) or [])
        # Sub-axis labels (preserve declared order if present in YAML)
        declared_sub_axes = raw.get("sub_axes")
        if isinstance(declared_sub_axes, dict):
            sub_axes = tuple(declared_sub_axes.keys())
        else:
            # Infer from per-term annotations
            seen: list[str] = []
            for sa in term_sub_axes.values():
                if sa not in seen:
                    seen.append(sa)
            sub_axes = tuple(seen)
        return _NormalisedLexicon(
            name=name,
            weighted_terms=weighted,
            term_sub_axes=term_sub_axes,
            sub_axes=sub_axes,
            intensifiers=intensifiers,
            hedges=hedges,
        )

    # Legacy shape: hawkish_phrases / dovish_phrases / hedges
    weighted = {}
    for phrase, w in (raw.get("hawkish_phrases") or {}).items():
        weighted[phrase] = float(w)
    for phrase, w in (raw.get("dovish_phrases") or {}).items():
        weighted[phrase] = float(w)
    return _NormalisedLexicon(
        name=name,
        weighted_terms=weighted,
        term_sub_axes={},
        sub_axes=(),
        intensifiers=(),
        hedges=tuple(raw.get("hedges") or []),
    )


class Scorer:
    """Loads lexicons by name from a directory and scores arbitrary text.

    The scorer caches loaded lexicons in-process; mutating a YAML on disk
    after first load does not affect already-running scoring (intentional —
    rebuilds require restart, matching the lexicon-version invariant).
    """

    def __init__(self, lexicon_dir: Path | None = None) -> None:
        self._lexicon_dir = lexicon_dir or Path("data/lexicons")
        self._cache: dict[str, _NormalisedLexicon] = {}

    def _load(self, lexicon_name: str) -> _NormalisedLexicon:
        if lexicon_name in self._cache:
            return self._cache[lexicon_name]
        path = self._lexicon_dir / f"{lexicon_name}.yaml"
        if not path.exists():
            raise KeyError(
                f"Lexicon {lexicon_name!r} not found at {path}",
            )
        raw = yaml.safe_load(path.read_text())
        lex = _normalise_lexicon_yaml(raw, fallback_name=lexicon_name)
        self._cache[lexicon_name] = lex
        return lex

    def score_post(self, *, text: str, lexicon_name: str) -> LexiconScore:
        """Score a piece of text on the named lexicon. Returns a generic
        `LexiconScore` with the signed value in [-1, 1] and a hits dict
        recording which terms matched (for audit + debugging).

        Multi-axis lexicons additionally populate `sub_axis_scores` with
        the (clamped) per-axis score; the top-level `value` is the average
        of non-zero sub-axis values."""
        lex = self._load(lexicon_name)
        lowered = text.lower()

        # Per-sub-axis raw accumulator (single-axis lexicons collapse to
        # one bucket via the empty key).
        per_sub_axis: dict[str, float] = {}
        if lex.sub_axes:
            for sa in lex.sub_axes:
                per_sub_axis[sa] = 0.0
        else:
            per_sub_axis[""] = 0.0

        hits: dict[str, int] = {}
        for term, weight in lex.weighted_terms.items():
            tlow = term.lower()
            if tlow in lowered:
                count = lowered.count(tlow)
                hits[term] = count
                bucket = lex.term_sub_axes.get(term, "")
                if bucket not in per_sub_axis:
                    # Multi-axis lexicon but term lacked an annotation —
                    # fall back to overall bucket.
                    bucket = next(iter(per_sub_axis.keys()))
                per_sub_axis[bucket] += weight

        # Modifiers (apply uniformly across all sub-axes — they're a
        # whole-utterance effect, not per-axis)
        intensifier_count = sum(1 for i in lex.intensifiers if i.lower() in lowered)
        intensifier_factor = (
            min(1.5, 1.0 + 0.15 * intensifier_count) if intensifier_count else 1.0
        )
        hedge_count = sum(1 for h in lex.hedges if h.lower() in lowered)
        hedge_factor = (
            max(0.4, 1.0 - 0.2 * hedge_count) if hedge_count else 1.0
        )

        # Apply modifiers + clamp each bucket
        clamped_per_axis = {
            sa: max(-1.0, min(1.0, v * intensifier_factor * hedge_factor))
            for sa, v in per_sub_axis.items()
        }

        if lex.sub_axes:
            # Top-level value: mean of NON-ZERO sub-axis scores (so the score
            # reflects 'how strongly does any axis fire', not diluted by
            # silent axes).
            nonzero = [v for v in clamped_per_axis.values() if v != 0.0]
            top = sum(nonzero) / len(nonzero) if nonzero else 0.0
            return LexiconScore(
                value=max(-1.0, min(1.0, top)),
                hits=hits,
                sub_axis_scores=clamped_per_axis,
            )
        else:
            return LexiconScore(
                value=clamped_per_axis[""], hits=hits,
            )


def score_sentence(text: str, *, lexicon: Lexicon) -> float:
    """Score a sentence on hawkish-dovish in [-1, +1]. Hedges dampen magnitude."""
    lowered = text.lower()
    raw = 0.0
    for phrase, weight in lexicon.hawkish_phrases.items():
        if phrase in lowered:
            raw += weight
    for phrase, weight in lexicon.dovish_phrases.items():
        if phrase in lowered:
            raw += weight  # weight is already negative

    hedge_count = sum(1 for h in lexicon.hedges if h in lowered)
    if hedge_count > 0:
        raw *= max(0.4, 1.0 - 0.2 * hedge_count)

    return max(-1.0, min(1.0, raw))


@dataclass(frozen=True)
class SpeechScoreResult:
    score: float
    n_policy_sentences: int


POLICY_RELEVANT_THRESHOLD = 0.05


def score_speech(sentences: list[str], *, lexicon: Lexicon) -> SpeechScoreResult:
    """Aggregate a speech: mean of policy-relevant sentence scores."""
    scored = [score_sentence(s, lexicon=lexicon) for s in sentences]
    policy = [x for x in scored if abs(x) > POLICY_RELEVANT_THRESHOLD]
    if not policy:
        return SpeechScoreResult(score=0.0, n_policy_sentences=0)
    return SpeechScoreResult(
        score=sum(policy) / len(policy),
        n_policy_sentences=len(policy),
    )


# Common abbreviations that should NOT split a sentence
_ABBREV = {"U.S.", "Mr.", "Mrs.", "Dr.", "Sen.", "Rep.", "Gov.", "e.g.", "i.e.", "vs.", "etc."}


def split_sentences(text: str) -> list[str]:
    """Split a transcript into sentences, respecting common abbreviations."""
    placeholder_text = text
    for abbr in _ABBREV:
        placeholder_text = placeholder_text.replace(abbr, abbr.replace(".", "<DOT>"))
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", placeholder_text)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]
