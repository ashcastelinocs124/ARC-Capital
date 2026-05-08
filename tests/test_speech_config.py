from castelino.config import get_settings


def test_speech_config_has_defaults():
    s = get_settings()
    assert s.speech.enabled is True
    assert s.speech.deviation_threshold_sigma == 1.5
    assert s.speech.lexicon_version == "hawkish_dovish_v1"
    assert s.speech.window_size == 5
    assert "powell" in [sp.id for sp in s.speech.speakers]


def test_speech_config_speaker_has_full_name():
    s = get_settings()
    powell = next(sp for sp in s.speech.speakers if sp.id == "powell")
    assert powell.full_name == "Jerome H. Powell"
    assert "Chair" in powell.role
