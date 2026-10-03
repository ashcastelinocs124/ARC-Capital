"""SectorSentimentCfg defaults + yaml override."""

from castelino.config import SectorSentimentCfg, get_settings


def test_defaults():
    cfg = SectorSentimentCfg()
    assert cfg.enabled is True
    assert cfg.euphoric_threshold == 0.3
    assert cfg.fearful_threshold == -0.3
    assert cfg.universe_cache_hours == 24
    assert cfg.fundamentals_cache_hours == 24
    assert cfg.top_n_per_sector == 10
    assert cfg.min_history_for_zscore == 20


def test_settings_has_block():
    s = get_settings()
    assert isinstance(s.sector_sentiment, SectorSentimentCfg)
