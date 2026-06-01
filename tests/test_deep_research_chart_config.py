from castelino.config import get_settings


def test_chart_config_defaults():
    dr = get_settings().deep_research
    assert dr.max_charts == 4
    assert dr.chart_lookback_days_default == 365
