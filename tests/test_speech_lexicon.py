from pathlib import Path
import yaml


def test_lexicon_v1_loads_with_required_sections():
    path = Path("data/lexicons/hawkish_dovish_v1.yaml")
    data = yaml.safe_load(path.read_text())
    assert data["version"] == "v1"
    assert isinstance(data["hawkish_phrases"], dict)
    assert isinstance(data["dovish_phrases"], dict)
    assert isinstance(data["hedges"], list)
    assert all(0.0 < w <= 1.0 for w in data["hawkish_phrases"].values())
    assert all(-1.0 <= w < 0.0 for w in data["dovish_phrases"].values())


def test_lexicon_has_at_least_30_signal_phrases():
    path = Path("data/lexicons/hawkish_dovish_v1.yaml")
    data = yaml.safe_load(path.read_text())
    total = len(data["hawkish_phrases"]) + len(data["dovish_phrases"])
    assert total >= 30, "lexicon too thin to be meaningful"
