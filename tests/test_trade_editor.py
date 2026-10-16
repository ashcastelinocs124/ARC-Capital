from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from castelino import benchmark
from castelino.agents.trade import editor, llm
from castelino.agents.trade.models import (
    ChartOption,
    ChartSpec,
    Frame,
    Report,
    ReportSection,
    Round,
    StandIn,
    StepError,
    TradeIdea,
    Turn,
)
from castelino.agents.weekly.editor import AnthropicEditorClient
from castelino.config import get_settings
from tests.trade_fakes import FakeClient, fact, parsed

FACTS = [
    fact("F1.1", "INDA fell 13.0% this year", [-13.0]),
    fact("C1.1", "Waterfall: currency part -5.3", [-5.3]),
]


def idea():
    spec = ChartSpec(
        section="bear",
        form="waterfall",
        series=["yahoo:INDA", "yahoo:INR=X"],
        window_days=300,
        threshold=None,
        title="Where INDA's loss came from",
        why="w",
        agent_pick=True,
    )
    option = ChartOption(
        id="bear-1-1", spec=spec, file="bear-1-1.png", fact_ids=["C1.1"], chosen=True
    )
    return TradeIdea(
        id="i1",
        idea="India is an AI hedge",
        created_at="t",
        updated_at="t",
        frame=Frame(
            title="India",
            thesis="India diversifies AI",
            stand_ins=[StandIn(ticker="INDA", role="subject", label="India")],
            horizon_months=12,
            prove_wrong=["corr above 0.6"],
            why_now_query="q",
        ),
        turns=[Turn(side="bull", round=0, text="India holds little AI.", fact_ids=[])],
        rounds=[Round(n=1, options=[option])],
        facts=FACTS,
    )


def report(watch="Watch the rupee."):
    secs = [
        ReportSection(key=k, heading=k.title(), paragraphs=["INDA fell 13.0%."], fact_ids=["F1.1"])
        for k in ("bull", "bear", "question", "technical", "read")
    ]
    return Report(
        title="India is an AI hedge",
        subtitle="s",
        introduction=["The idea.", "How we tested it."],
        takeaways=["a", "b", "c"],
        sections=secs,
        what_to_watch=watch,
        changes=[],
    )


class FakeEditor:
    def __init__(self, *outs):
        self.outs, self.seen, self.last_usage = list(outs), [], (1000, 500)

    def parse(self, *, system, messages, schema):
        self.seen.append(messages)
        return self.outs.pop(0), []


def test_anthropic_client_logs_under_its_agent_label_and_keeps_usage():
    class Out(BaseModel):
        ok: bool

    resp = SimpleNamespace(
        stop_reason="end_turn",
        parsed_output=Out(ok=True),
        content=[],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
    )
    c = object.__new__(AnthropicEditorClient)
    c.model, c.effort, c.max_tokens, c.agent = "claude-opus-5-5", "high", 100, "trade_editor"
    c.last_usage = (None, None)
    c.client = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(parse=lambda **kw: resp))
    )
    out, _ = c.parse(system="s", messages=[], schema=Out)
    assert out.ok and c.last_usage == (11, 7)
    assert benchmark.read("calls", date.today().isoformat())[-1]["agent"] == "trade_editor"


def test_brief_has_the_chosen_chart_and_the_base_draft():
    text = editor.brief(idea(), "My edited draft text.")
    assert "Where INDA's loss came from" in text and "[C1.1]" in text
    assert "My edited draft text." in text and "keep the user's wording" in text


def test_write_retries_once_with_the_errors():
    fe = FakeEditor(report(watch="A 9.9% move."), report())
    m = llm.Meter()
    out = editor.write(idea(), m, client=fe)
    assert out.what_to_watch == "Watch the rupee."
    assert "9.9%" in fe.seen[1][-1]["content"]
    assert m.total == pytest.approx(2 * (1000 * 4 + 500 * 20) / 1e6)


def test_write_fails_after_two_bad_reports():
    bad = report(watch="A 9.9% move.")
    with pytest.raises(StepError, match="9.9%"):
        editor.write(idea(), llm.Meter(), client=FakeEditor(bad, bad))


def test_revise_changes_only_the_part(monkeypatch):
    rev = editor.Revision(paragraphs=["The rupee took 5.3 points off."], fact_ids=["C1.1"])
    c = FakeClient([parsed(rev)])
    monkeypatch.setattr(llm, "_client", lambda m: c)
    i = idea().model_copy(update={"report": report()})
    out, model = editor.revise(i, "bear", "Lead with the rupee", llm.Meter())
    assert out.sections[1].paragraphs == ["The rupee took 5.3 points off."]
    assert out.sections[0] == i.report.sections[0]
    assert model == get_settings().trade_lab.talk_model


def test_the_editor_writes_for_readers_not_with_internal_labels():
    """Headings were fixed labels (The bull case, Your question, tested) and the intro said "in the user's
    words"; the draft is for Substack readers (user feedback, 2026-10-16)."""
    assert "Substack readers" in editor.SYSTEM
    assert "The bull case" not in editor.SYSTEM and "the user's words" not in editor.SYSTEM


def test_revise_can_retitle_a_section(monkeypatch):
    rev = editor.Revision(
        paragraphs=["The rupee took 5.3 points off."], fact_ids=["C1.1"], heading="The rupee did it"
    )
    c = FakeClient([parsed(rev)])
    monkeypatch.setattr(llm, "_client", lambda m: c)
    i = idea().model_copy(update={"report": report()})
    out, _ = editor.revise(i, "bear", "Give it a heading readers get", llm.Meter())
    assert out.sections[1].heading == "The rupee did it"
    assert out.sections[0].heading == i.report.sections[0].heading


def test_revise_takes_fact_ids_out_of_the_published_text(monkeypatch):
    """GLM-5.3 wrote "[C1.16]" into its edit in testing; ids in the text would be published."""
    rev = editor.Revision(paragraphs=["The rupee took 5.3 points off [C1.1]."], fact_ids=["C1.1"])
    c = FakeClient([parsed(rev)])
    monkeypatch.setattr(llm, "_client", lambda m: c)
    i = idea().model_copy(update={"report": report()})
    out, _ = editor.revise(i, "bear", "Lead with the rupee", llm.Meter())
    assert out.sections[1].paragraphs == ["The rupee took 5.3 points off."]


def test_revise_hands_the_edit_to_the_fallback_after_two_failed_checks(monkeypatch):
    """Claude Haiku 5.5 makes slight edits; Claude Sonnet 5.5 takes the ones it fails twice (2026-10-16)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    bad = editor.Revision(paragraphs=["The rupee fell 77.7%."], fact_ids=["C1.1"])  # in no fact
    good = editor.Revision(paragraphs=["The rupee took 5.3 points off."], fact_ids=["C1.1"])
    c = FakeClient([parsed(bad), parsed(bad), parsed(good)])
    monkeypatch.setattr(llm, "_client", lambda m: c)
    i = idea().model_copy(update={"report": report()})
    out, model = editor.revise(i, "bear", "Lead with the rupee", llm.Meter())
    cfg = get_settings().trade_lab
    assert [call[1]["model"] for call in c.calls] == [cfg.talk_model] * 2 + [
        cfg.fallback_talk_model
    ]
    assert model == cfg.fallback_talk_model
    assert out.sections[1].paragraphs == ["The rupee took 5.3 points off."]


def test_round_two_keeps_figures_the_user_typed_in_substack():
    hand = report(watch="Watch the rupee near 7.5%.")
    base = "I think the rupee breaks 7.5% soon."
    out = editor.write(idea(), llm.Meter(), client=FakeEditor(hand), base_draft=base)
    assert out.what_to_watch == "Watch the rupee near 7.5%."
    assert any("7.5%" in c and "yours" in c for c in out.changes)
