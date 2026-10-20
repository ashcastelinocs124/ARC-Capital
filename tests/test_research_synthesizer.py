import pytest

from castelino.agents.research.deep import synthesizer
from castelino.agents.research.deep.models import (
    Finding,
    PointDraft,
    ReportDraft,
    ResearchSession,
    StepError,
)
from castelino.agents.trade import llm
from tests.research_fakes import agent, fact


class FakeEditor:
    def __init__(self, *drafts):
        self.drafts, self.calls, self.last_usage = list(drafts), [], (1000, 200)

    def parse(self, *, system, messages, schema):
        self.calls.append(list(messages))
        return self.drafts.pop(0), []


def session():
    b = agent(
        "B",
        facts=[fact("B1", "Large firms: 27% use AI in 2026", [27.0])],
        findings=[Finding(id="B-f1", claim="27% of large firms", fact_ids=["B1"])],
    )
    c = agent("C", facts=[], findings=[]).model_copy(update={"error": "boom"})
    return ResearchSession(
        id="s",
        topic="AI adoption",
        question="How fast are US firms adopting AI?",
        agents=[agent("A"), b, c],
        created_at="x",
        updated_at="x",
    )


def draft(body_a="The survey puts it at 9.2% [A1].", owner="A · Adoption rate"):
    return ReportDraft(
        title="AI adoption is rising",
        subtitle="US firms since 2022",
        points=[
            PointDraft(
                agent=owner, headline="AI use reached 9.2% of firms.", body=body_a, fact_ids=["A1"]
            ),
            PointDraft(
                agent="Researcher B",
                headline="Large firms lead at 27%.",
                body="27% of large firms use AI.",
                fact_ids=["B1"],
            ),
        ],
        caveats=["Survey data only."],
    )


def test_write_numbers_points_normalizes_owners_and_strips_ids():
    meter = llm.Meter()
    rep = synthesizer.write(session(), meter, client=FakeEditor(draft()))
    p1, p2 = rep.points
    assert (p1.id, p1.agent, p1.version) == ("p1", "A", 1) and p2.agent == "B"
    assert p1.body == "The survey puts it at 9.2%."
    assert meter.total > 0 and rep.chart_specs == [] and rep.points[0].chart is None


def test_the_writer_leaves_charts_to_the_chart_agent():
    assert "chart_specs" not in ReportDraft.model_fields and "chart" not in synthesizer.SYSTEM


def test_one_retry_with_the_guard_errors():
    ed = FakeEditor(draft(body_a="It is 9.7%."), draft())
    rep = synthesizer.write(session(), llm.Meter(), client=ed)
    assert rep.points[0].body.endswith("9.2%.")
    assert ed.calls[1][-1]["content"].startswith("Fix these and write the whole report again")


def test_two_failures_are_a_step_error():
    with pytest.raises(StepError, match="number check"):
        synthesizer.write(session(), llm.Meter(), client=FakeEditor(draft("9.7%."), draft("9.8%.")))


def test_brief_has_findings_and_facts_and_skips_failed_agents():
    text = synthesizer.brief(session())
    assert "Researcher A · Adoption rate" in text and "[A1] AI use reached 9.2% of firms" in text
    assert "Researcher C" not in text


def test_owner_letter():
    names = ("B", "b · Who leads", "Researcher C", " D ", "Agent B", "agent: C", "researcher E")
    got = [synthesizer.owner_letter(x) for x in names]
    assert got == ["B", "B", "C", "D", "B", "C", "E"]
