from castelino.agents import base
from castelino.agents.update import editor
from castelino.agents.update.models import Fact, Finding, MorningNote, Point, SeriesRef


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
    assert model == "gpt-6-sol" and "exactly 3" in system and "exactly 5 items" in system
    assert "[macro-1] (macro) [chartable] 10y up" in user
    assert "evidence:\n    [M1] DGS10 (rates): 1d +4.00bp" in user
    assert "item 1: 9%" in user and "mem" in user


def test_item_bodies_run_what_why_how_without_labels():
    system = editor.UpdateEditor().system_prompt()
    assert "about 400 words" in system and "Never label or head the" in system
    assert "What happened" in system and "Why it happened" in system
    assert "How it came about" in system and "Background evidence" in system
    assert "compare with the prior reading" in system
    assert "Never write about what did not happen" in system
    assert "no claims about history the evidence doesn't show" in system


def test_prompt_lists_chart_forms_and_tags_facts():
    system = editor.UpdateEditor().system_prompt()
    for form in (
        "range:",
        "movers:",
        "ladder:",
        "columns:",
        "dumbbell:",
        "vs_expected:",
        "compare:",
        "line:",
    ):
        assert form in system
    assert "{history}" in system and "{series}" in system  # format() left them single-braced
    daily = Fact(
        id="S1",
        text="t",
        numbers=[],
        provenance="data",
        source_title="s",
        source_url="u",
        series=SeriesRef(kind="daily", provider="yahoo", id="X", label="X"),
    )
    hist = daily.model_copy(
        update={
            "series": SeriesRef(
                kind="release",
                provider="fred",
                id="C",
                label="CPI y/y",
                points=[Point(label=str(i), value=i) for i in range(3)],
            )
        }
    )
    assert editor._tag(daily) == " {series}" and editor._tag(hist) == " {history}"
    assert editor._tag(daily.model_copy(update={"series": None})) == ""


def test_prompt_carries_the_arc_house_voice():
    system = editor.UpdateEditor().system_prompt()
    assert system.endswith(editor.STYLE) and "## ARC house voice" in system
    assert "**What to watch:**" in system and "no dashes" in system
    assert "never a recommendation" in system and "Describe, don't recommend" not in system
