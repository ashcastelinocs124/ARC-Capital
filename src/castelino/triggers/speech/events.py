"""Per-event JSON records for speech listener output."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from castelino.config import get_settings
from castelino.memory.schemas import TriggerRecord


class SpeechEventRecord(BaseModel):
    event_id: str
    speaker_id: str
    started_at: datetime
    scored_sentences: list[tuple[str, float]] = Field(default_factory=list)
    triggers_fired: list[TriggerRecord] = Field(default_factory=list)


def _events_dir(root: Path | None = None) -> Path:
    if root is not None:
        return root / "speech_events"
    return get_settings().resolved_paths.data / "speech_events"


def save_event_record(rec: SpeechEventRecord, *, root: Path | None = None) -> Path:
    d = _events_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{rec.event_id}.json"
    path.write_text(rec.model_dump_json(indent=2))
    return path
