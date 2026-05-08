import pytest
from datetime import datetime, timedelta, UTC

from castelino.triggers.speech.persona import (
    build_persona_from_speeches, load_persona, save_persona,
)
from castelino.triggers.speech.scrapers.fed import ParsedSpeech


def _ps(text: str, days_ago: int) -> ParsedSpeech:
    return ParsedSpeech(
        speaker="Jerome H. Powell",
        date=datetime.now(UTC) - timedelta(days=days_ago),
        venue="Test",
        title="t",
        text=text,
        url=f"https://x/{days_ago}",
    )


def test_build_persona_aggregates_correctly():
    speeches = [
        _ps("We will be patient. Accommodative for now. Considerable progress.", 30),
        _ps("The economy is balanced. Risks remain two-sided.", 60),
        _ps("Further firming may be warranted. Inflation persistent.", 10),
    ]
    persona = build_persona_from_speeches(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair, Federal Reserve",
        speeches=speeches,
        lexicon_version="hawkish_dovish_v1",
    )
    assert persona.speaker_id == "powell"
    assert len(persona.speeches_in_window) == 3
    assert persona.baseline_vector.hawkish_dovish_std > 0.0
    assert persona.lexicon_version == "hawkish_dovish_v1"


def test_save_and_load_persona_round_trip(tmp_path):
    from castelino.triggers.speech.models import (
        BaselineVector, SpeakerPersona,
    )
    p = SpeakerPersona(
        speaker_id="powell", full_name="J.P.", role="Chair",
        baseline_window_days=365, last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=BaselineVector(
            hawkish_dovish_mean=0.0, hawkish_dovish_std=0.1,
            key_phrase_frequencies={}, hedging_density=0.1,
        ),
        lexicon_version="hawkish_dovish_v1",
    )
    save_persona(p, root=tmp_path)
    loaded = load_persona("powell", root=tmp_path)
    assert loaded == p
