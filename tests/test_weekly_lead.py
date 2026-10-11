import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.weekly import lead
from castelino.agents.weekly.models import DeepPlan, SubAgentSpec, Trend

TRENDS = [Trend(title=f"t{i}", why="w") for i in range(12)]


def spec(name, trends, related=(), tools=("fred_series",)):
    return SubAgentSpec(
        name=name,
        description="d",
        goal="g",
        tools=list(tools),
        related=list(related),
        trends=list(trends),
    )


def five_desks(n=10):
    titles = [t.title for t in TRENDS[:n]]
    return [spec(f"Desk {k}", titles[k * 2 : k * 2 + 2]) for k in range(5)]


def test_validate_caps_at_five_desks_and_twelve_trends():
    desks = five_desks(10) + [spec("Sixth desk", ["t10", "t11"])]
    out = lead.validate_plan(DeepPlan(trends=TRENDS + [Trend(title="t12", why="w")], agents=desks))
    assert len(out.agents) == 5 and len(out.trends) == 12
    # t10/t11 belonged only to the dropped sixth desk: given to the desk with the fewest trends
    owned = [t for a in out.agents for t in a.trends]
    assert sorted(owned) == sorted(t.title for t in out.trends)


def test_validate_drops_duplicates_unknown_related_and_unknown_trends():
    desks = five_desks(10)
    desks[0] = spec("Desk 0", ["t0", "t1", "ghost"], related=["Ghost desk", "Desk 1", "Desk 0"])
    desks.insert(1, spec("desk 0", ["t2"]))  # duplicate by case
    out = lead.validate_plan(DeepPlan(trends=TRENDS[:10], agents=desks))
    assert [a.name for a in out.agents] == [f"Desk {k}" for k in range(5)]
    assert out.agents[0].trends == ["t0", "t1"] and out.agents[0].related == ["Desk 1"]


def test_a_trend_claimed_twice_belongs_to_its_first_desk():
    desks = five_desks(10)
    desks[1] = spec("Desk 1", ["t2", "t3", "t0"])
    out = lead.validate_plan(DeepPlan(trends=TRENDS[:10], agents=desks))
    assert out.agents[1].trends == ["t2", "t3"]


def test_short_plan_is_rejected():
    with pytest.raises(lead.ShortPlanError, match="9 trends"):
        lead.validate_plan(DeepPlan(trends=TRENDS[:9], agents=five_desks(9)))


def test_validate_rejects_empty_desk():
    with pytest.raises(RuntimeError, match="no usable sub-agents"):
        lead.validate_plan(DeepPlan(trends=TRENDS[:10], agents=[]))


def test_plan_retries_once_when_short_and_names_the_shortfall():
    fake = FakeLLMClient()
    replies = [
        DeepPlan(trends=TRENDS[:6], agents=five_desks(6)),
        DeepPlan(trends=TRENDS[:10], agents=five_desks(10)),
    ]
    fake.register("DeepPlan", lambda s, u: replies.pop(0))
    set_llm_client(fake)
    try:
        out = lead.plan("2026-W41", "## 2026-10-05: Yields jump", "- theme")
    finally:
        set_llm_client(None)
    assert len(out.trends) == 10 and len(fake.call_log) == 2
    _schema, model, system, user = fake.call_log[0]
    assert model == "gpt-6-sol" and "## 2026-10-05: Yields jump" in user and "2026-W41" in user
    assert "10-12 trends" in system and "5 specialist" in system
    assert "only 6 trends" in fake.call_log[1][3]
