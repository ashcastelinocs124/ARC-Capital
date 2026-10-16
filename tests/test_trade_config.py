from castelino.config import get_settings


def test_trade_lab_defaults_match_the_spec():
    t = get_settings().trade_lab
    assert t.orchestrator_model == "gpt-6-sol"
    assert t.debate_model == t.framer_model == "deepseek/deepseek-v4-pro"
    assert t.talk_model == "anthropic/claude-haiku-5.5"
    assert t.fallback_talk_model == "anthropic/claude-sonnet-5.5"
    assert t.desk_model == t.chart_model == t.decide_model == "gpt-6-luna"
    assert t.editor_model == "claude-opus-5-5" and t.editor_effort == "high"
    assert (t.opening_calls, t.rebuttal_calls, t.news_calls, t.technical_calls) == (8, 2, 12, 16)
    assert t.talk_research_calls == 4
    assert (t.cost_cap_usd, t.concurrency, t.decide_threshold) == (5.0, 2, 0.5)
    assert t.openrouter_provider == {
        "data_collection": "deny",
        "require_parameters": True,
        "sort": "price",
    }
    assert t.data_dir == "data/trades"
