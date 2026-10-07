from castelino.agents import base
from castelino.agents.update import orchestrator
from castelino.agents.update.models import Briefs, Finding, FollowUp, Review


def test_plan_and_review_use_sol(monkeypatch):
    fake = base.FakeLLMClient()
    fake.register("Briefs", lambda s, u: Briefs(macro="m", news="n", alt="a"))
    fake.register(
        "Review",
        lambda s, u: Review(done=False, followups=[FollowUp(agent="macro", ask="oil?")]),
    )
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    b = orchestrator.plan("## Notes\nInflation theme", "", "2026-10-07")
    assert b.macro == "m"
    assert "Inflation theme" in fake.call_log[-1][3] and fake.call_log[-1][1] == "gpt-6-sol"
    f = Finding(
        id="news-1",
        agent="news",
        claim="Oil +4%",
        provenance="reported",
        source_title="s",
        source_url="u",
        fact_ids=["N1"],
    )
    r = orchestrator.review([f], 0)
    assert r.followups[0].agent == "macro"
    schema, model, system, user = fake.call_log[-1]
    assert schema == "Review" and model == "gpt-6-sol" and "[news-1] (news) Oil +4%" in user
