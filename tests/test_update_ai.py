import pytest

from castelino.agents import base
from castelino.agents.update import ai
from castelino.agents.update.models import FindingDraft, FindingDrafts

TEXT = "- A lab released a new model with 40% lower pricing ([reuters.com](https://r.com/x))"


def fake_search(system, user, model=None):
    fake_search.calls.append((system, user, model))
    i = TEXT.index("([reuters")
    return TEXT, [("Reuters", "https://r.com/x", i, i + 20)]


def test_run_builds_ai_findings(monkeypatch):
    fake_search.calls = []
    fake = base.FakeLLMClient()
    fake.register(
        "FindingDrafts",
        lambda s, u: FindingDrafts(
            findings=[FindingDraft(claim="New model", figure=40.0, unit="%", fact_ids=["I1"])]
        ),
    )
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    out = ai.run("chips focus", "any launches?", search=fake_search)
    f = out.findings[0]
    assert f.agent == "ai" and f.provenance == "reported" and f.source_title == "Reuters"
    system, user, model = fake_search.calls[0]
    assert "chips focus" in user and "any launches?" in user and "chips" in user
    assert "no anonymous" in system and model == "gpt-6-luna"


def test_no_cited_stories_raises():
    with pytest.raises(RuntimeError, match="no cited stories"):
        ai.run("x", search=lambda *a, **k: ("uncited text", []))
