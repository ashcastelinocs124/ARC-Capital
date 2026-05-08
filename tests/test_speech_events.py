from datetime import datetime, UTC
from castelino.triggers.speech.events import SpeechEventRecord, save_event_record


def test_save_event_record_round_trip(tmp_path):
    rec = SpeechEventRecord(
        event_id="fomc-2026-04",
        speaker_id="powell",
        started_at=datetime.now(UTC),
        scored_sentences=[("Hello.", 0.0), ("Further firming.", 0.7)],
        triggers_fired=[],
    )
    path = save_event_record(rec, root=tmp_path)
    loaded = SpeechEventRecord.model_validate_json(path.read_text())
    assert loaded.event_id == "fomc-2026-04"
    assert len(loaded.scored_sentences) == 2
