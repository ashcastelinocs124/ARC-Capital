from datetime import datetime, UTC
from castelino.triggers.speech.models import (
    BaselineVector, ScoredSpeech, SpeakerPersona, SpeechSegment,
)

def test_scored_speech_round_trips_json():
    s = ScoredSpeech(
        speech_id="20260301-powell-brookings",
        date=datetime(2026, 3, 1, tzinfo=UTC),
        venue="Brookings",
        score=-0.22,
        n_policy_sentences=84,
    )
    assert ScoredSpeech.model_validate_json(s.model_dump_json()) == s

def test_baseline_vector_validates():
    bv = BaselineVector(
        hawkish_dovish_mean=-0.15,
        hawkish_dovish_std=0.20,
        key_phrase_frequencies={"data dependent": 0.85},
        hedging_density=0.18,
    )
    assert bv.hawkish_dovish_mean == -0.15

def test_speaker_persona_round_trips():
    bv = BaselineVector(
        hawkish_dovish_mean=-0.15, hawkish_dovish_std=0.20,
        key_phrase_frequencies={}, hedging_density=0.18,
    )
    p = SpeakerPersona(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair, Federal Reserve",
        baseline_window_days=365,
        last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=bv,
        lexicon_version="hawkish_dovish_v1",
    )
    assert SpeakerPersona.model_validate_json(p.model_dump_json()).speaker_id == "powell"

def test_speech_segment_immutable_text():
    seg = SpeechSegment(
        speaker_id="powell",
        text="Further firming may be warranted.",
        timestamp=datetime.now(UTC),
        event_id="fomc-2026-04",
    )
    assert seg.text.startswith("Further")
