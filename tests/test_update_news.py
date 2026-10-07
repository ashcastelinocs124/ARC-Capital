import pytest

from castelino.agents import base
from castelino.agents.update import news
from castelino.agents.update.models import FindingDraft, FindingDrafts

TEXT = "- Oil rose 4% after OPEC cut output ([reuters.com](https://r.com/x))"


def fake_search(system, user, model=None):
    fake_search.calls.append((user, model))
    i = TEXT.index("([reuters")
    return TEXT, [("Reuters", "https://r.com/x", i, i + 20)]


def test_run_builds_reported_findings(monkeypatch):
    fake_search.calls = []
    fake = base.FakeLLMClient()
    fake.register(
        "FindingDrafts",
        lambda s, u: FindingDrafts(
            findings=[FindingDraft(claim="Oil up on OPEC", figure=4.0, unit="%", fact_ids=["N1"])]
        ),
    )
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    out = news.run("energy focus", "check oil", search=fake_search)
    assert out.findings[0].provenance == "reported" and out.findings[0].source_title == "Reuters"
    assert "energy focus" in fake_search.calls[0][0] and "check oil" in fake_search.calls[0][0]
    assert fake_search.calls[0][1] == "gpt-6-luna"


def test_no_cited_stories_raises():
    with pytest.raises(RuntimeError, match="no cited stories"):
        news.run("x", search=lambda *a, **k: ("uncited text", []))
