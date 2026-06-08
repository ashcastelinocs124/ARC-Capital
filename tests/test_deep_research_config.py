from castelino.config import get_settings


def test_deep_research_config_defaults():
    cfg = get_settings()
    dr = cfg.deep_research
    assert dr.max_sub_questions == 6
    assert dr.max_rounds == 2
    assert dr.max_sonar_calls == 15
    assert dr.concurrency == 3
    assert dr.clarify_max_questions == 3
    assert dr.reasoning_tier == "reasoning"
    assert dr.fast_tier == "fast"
    assert dr.reports_dir == "data/research"
