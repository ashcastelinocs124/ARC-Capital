import pytest

from castelino.agents.weekly.editor import DeepEditor, answers_brief, desk_brief
from castelino.agents.weekly.models import (
    AgentRun,
    BoardPost,
    DeepPlan,
    Grill,
    GrillExchange,
    GrillQuestion,
    SubAgentSpec,
    Trend,
    WeeklyFinding,
    WeeklyReport,
)
from tests.weekly_fixtures import fact

REPORT = WeeklyReport(title="T", subtitle="S", bullets=[], watch="W", sections=[])


class FakeEditorClient:
    def __init__(self, outs):
        self.outs, self.calls = list(outs), []

    def parse(self, *, system, messages, schema):
        self.calls.append([dict(m) for m in messages])
        out = self.outs.pop(0)
        if isinstance(out, Exception):
            raise out
        assert isinstance(out, schema)
        return out, [{"type": "text", "text": out.model_dump_json()}]


def test_conversation_is_append_only_across_grill_and_write():
    q = GrillQuestion(agent="Rates desk", finding_id="rates-desk-1", question="q")
    client = FakeEditorClient(
        [Grill(done=False, questions=[q]), Grill(done=True, questions=[]), REPORT, REPORT]
    )
    ed = DeepEditor(client)
    ed.open("desk")
    ed.followup("answers", last=True)
    ed.write(None)
    ed.write(["section 1: 9bp"])
    for before, after in zip(client.calls, client.calls[1:], strict=False):
        assert after[: len(before)] == before  # never edits history
    assert "section 1: 9bp" in client.calls[-1][-1]["content"]
    assert [m["role"] for m in ed.messages][-2:] == ["user", "assistant"]


def test_failed_call_leaves_user_turn_and_history_stays_valid():
    client = FakeEditorClient([RuntimeError("overloaded"), REPORT])
    ed = DeepEditor(client)
    with pytest.raises(RuntimeError):
        ed.open("desk")
    ed.write(None)  # consecutive user turns are allowed; nothing was rewritten
    assert [m["role"] for m in client.calls[1]] == ["user", "user"]


def test_desk_brief_lists_trends_findings_facts_and_board():
    spec = SubAgentSpec(
        name="Rates desk",
        description="d",
        goal="Explain 10y",
        tools=["fred_series"],
        related=[],
        trends=["Long end reprices"],
    )
    plan = DeepPlan(trends=[Trend(title="Long end reprices", why="biggest move")], agents=[spec])
    f = fact("A1", nums=(28,), text="DGS10 change +28bp")
    finding = WeeklyFinding(
        id="rates-desk-1",
        agent="Rates desk",
        claim="10y up 28bp",
        provenance="data",
        source_title="FRED DGS10",
        source_url="u",
        fact_ids=["A1"],
    )
    run = AgentRun(agent="Rates desk", facts=[f], findings=[finding], tool_calls=1)
    post = BoardPost(agent="Rates desk", note="10y up", fact_ids=["A1"])
    md = desk_brief("2026-W41", plan, [run], [post])
    for s in (
        "Long end reprices",
        "Rates desk",
        "Explain 10y",
        "[rates-desk-1] 10y up 28bp",
        "[A1] DGS10 change +28bp",
        "Board",
    ):
        assert s in md


def test_answers_brief_includes_new_facts():
    ex = GrillExchange(
        agent="Rates desk",
        finding_id="rates-desk-1",
        question="Growth?",
        answer="No.",
        fact_ids=["A2"],
    )
    md = answers_brief([ex], {"A2": fact("A2", text="T10YIE +3bp")})
    assert "Growth?" in md and "No." in md and "[A2] T10YIE +3bp" in md
