from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ScoredSpeech(BaseModel):
    speech_id: str
    date: datetime
    venue: str = ""
    score: float = Field(ge=-1.0, le=1.0)
    n_policy_sentences: int = Field(ge=0)


class BaselineVector(BaseModel):
    hawkish_dovish_mean: float = Field(ge=-1.0, le=1.0)
    hawkish_dovish_std: float = Field(ge=0.0)
    key_phrase_frequencies: dict[str, float] = Field(default_factory=dict)
    hedging_density: float = Field(ge=0.0, le=1.0)


class SpeakerPersona(BaseModel):
    speaker_id: str
    full_name: str
    role: str
    baseline_window_days: int = 365
    last_updated: datetime
    speeches_in_window: list[ScoredSpeech] = Field(default_factory=list)
    baseline_vector: BaselineVector
    lexicon_version: str


class SpeechSegment(BaseModel):
    speaker_id: str
    text: str
    timestamp: datetime
    event_id: str
