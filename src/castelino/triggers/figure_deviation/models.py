"""Core data models for the figure-deviation trigger.

Generalises the existing speech-listener types to multi-source (audio, X API,
future Sonar tweets), multi-lexicon (one figure can be scored on N lexicons in
parallel), and multi-figure (Fed speakers + Trump + future Bessent / Musk /
ECB officials). Design: docs/plans/2026-05-08-figure-deviation-design.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ────────────────────────── runtime post object ──────────────────────────────


class FigurePost(BaseModel):
    """One scored utterance — a tweet, a transcript sentence, or any future
    source type. The `source` field is a closed enum so an unknown source
    blows up at validation time rather than silently feeding the pipeline."""

    figure_id: str
    text: str
    ts: datetime
    source: Literal["audio", "x_api", "sonar_tweet"]
    event_id: str
    source_url: str | None = None
    raw_meta: dict = Field(default_factory=dict)


# ────────────────────────── persona-relative baselines ───────────────────────


class FigureBaseline(BaseModel):
    """Per-figure × per-lexicon baseline. The lexicon_version is load-bearing:
    if the version doesn't match the current lexicon YAML on startup, the
    orchestrator hard-fails and forces a `figure-refresh`. This prevents
    silent z-score corruption when lexicon weights change."""

    figure_id: str
    lexicon_name: str
    lexicon_version: int = Field(ge=1)
    mean: float
    std: float = Field(ge=0.0)
    n_samples: int = Field(ge=0)
    last_refreshed: datetime


# ────────────────────────── lexicon scoring output ───────────────────────────


class LexiconScore(BaseModel):
    """One lexicon's verdict on one post. `hits` carries which terms matched
    (for audit + debugging). `sub_axis_scores` populated only for multi-axis
    lexicons such as `regulatory_stance_v1` (crypto / oil / defence / tech)."""

    value: float = Field(ge=-1.0, le=1.0)
    hits: dict[str, int] = Field(default_factory=dict)
    sub_axis_scores: dict[str, float] | None = None


# ────────────────────────── trigger emission ─────────────────────────────────


class FigureDeviationTrigger(BaseModel):
    """The trigger object emitted into the pipeline at `current_event` when
    Stage A (z-score threshold) AND Stage B (LLM confirmation) both pass.

    `directional_tags` come from the lexicon config and act as a strong prior
    on the Hypothesis Agent's `expected_directional_moves`."""

    figure_id: str
    lexicon: str
    z: float
    direction: Literal["positive", "negative"]
    directional_tags: list[str]
    decisive_phrase: str
    confirmed_by_llm: bool
    confidence: float = Field(ge=0.0, le=1.0)
    window_post_ids: list[str]
