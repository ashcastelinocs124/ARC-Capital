import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.weekly import lead
from castelino.agents.weekly.models import DeepPlan, SubAgentSpec, Trend


def spec(name, related=(), tools=("fred_series",)):
    return SubAgentSpec(
        name=name, description="d", goal="g", tools=list(tools), related=list(related)
    )


def test_validate_drops_duplicates_unknown_related_and_caps_at_four():
    plan = DeepPlan(
        trends=[Trend(title=f"t{i}", why="w") for i in range(6)],
        agents=[
            spec("Rates desk", related=["Ghost desk", "Chips desk", "Rates desk"]),
            spec("rates desk"),  # duplicate by case
            spec("Chips desk"),
            spec("No tools desk", tools=()),
            spec("Energy desk"),
            spec("FX desk"),
            spec("Credit desk"),
        ],
    )
    out = lead.validate_plan(plan, max_agents=4)
    assert [a.name for a in out.agents] == ["Rates desk", "Chips desk", "Energy desk", "FX desk"]
    assert out.agents[0].related == ["Chips desk"]
    assert len(out.trends) == 4


def test_validate_rejects_empty_desk():
    with pytest.raises(RuntimeError, match="no usable sub-agents"):
        lead.validate_plan(DeepPlan(trends=[Trend(title="t", why="w")], agents=[]), max_agents=4)


def test_plan_uses_lead_model_and_week_markdown():
    fake = FakeLLMClient()
    fake.register(
        "DeepPlan",
        lambda s, u: DeepPlan(trends=[Trend(title="t", why="w")], agents=[spec("Rates desk")]),
    )
    set_llm_client(fake)
    try:
        out = lead.plan("2026-W41", "## 2026-10-05: Yields jump", "- theme")
    finally:
        set_llm_client(None)
    _schema, model, system, user = fake.call_log[0]
    assert model == "gpt-6-sol" and "## 2026-10-05: Yields jump" in user and "2026-W41" in user
    assert "at most 4" in system and out.agents[0].name == "Rates desk"
