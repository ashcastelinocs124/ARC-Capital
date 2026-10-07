from castelino.agents import base
from castelino.agents.update import editor
from castelino.agents.update.models import Fact, Finding, MorningNote, SeriesRef


def note():
    return MorningNote(
        headline="h", takeaways=["a", "b", "c"], items=[], themes_touched=[], new_themes=[]
    )


def test_prompt_marks_chartable_findings_and_shows_evidence(monkeypatch):
    fake = base.FakeLLMClient()
    fake.register("MorningNote", lambda s, u: note())
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    ref = SeriesRef(kind="daily", provider="fred", id="DGS10", label="10y")
    facts = [
        Fact(
            id="M1",
            text="DGS10 (rates): 1d +4.00bp",
            numbers=[4.0],
            provenance="data",
            source_title="FRED DGS10",
            source_url="u",
        )
    ]
    finds = [
        Finding(
            id="macro-1",
            agent="macro",
            claim="10y up",
            provenance="data",
            series=ref,
            source_title="FRED DGS10",
            source_url="u",
            fact_ids=["M1"],
        )
    ]
    editor.write_note(finds, facts, "mem", "long", ["item 1: 9%"])
    schema, model, system, user = fake.call_log[-1]
    assert model == "gpt-6-sol" and "exactly 3" in system and "3 to 5 items" in system
    assert "[macro-1] (macro) [chartable] 10y up" in user
    assert "evidence: DGS10 (rates): 1d +4.00bp" in user
    assert "item 1: 9%" in user and "mem" in user


def test_item_bodies_are_full_paragraphs_with_context_and_implication():
    system = editor.UpdateEditor().system_prompt()
    assert "80-120 words" in system
    assert "compares with the prior reading" in system and "why it matters" in system
    assert "no claims about history the evidence doesn't show" in system
