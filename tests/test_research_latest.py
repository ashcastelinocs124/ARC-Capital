"""The latest-data guardrail: each point needs a figure from this year (or last year, January to March).
The writer gets one retry; a point that still has only older data keeps it, says so and is marked."""

from datetime import date

import pytest

from castelino.agents.research.deep import critic, guard, store, synthesizer
from castelino.agents.research.deep.models import (
    Clarification,
    Finding,
    Point,
    PointDraft,
    ReportDraft,
)
from castelino.agents.trade import llm
from tests.research_fakes import agent, fact, xfact

TODAY = date(2026, 10, 20)
BY = {
    "A1": fact("A1", "Q3 2026: 55.9% of firms paid for AI", [55.9]),
    "A2": fact("A2", "2025: 44.0% of firms paid for AI", [44.0]),
    "A3": fact("A3", "Most firms paid for AI", [61.0]),
    "A4": xfact("A4", "analyst", "61% of my clients use AI", [61.0]),
}


def point(*ids, body="Text."):
    return Point(id="p1", agent="A", headline="h", body=body, fact_ids=list(ids))


def test_the_fresh_year_is_this_year_or_last_year_until_april():
    assert guard.fresh_year(TODAY) == 2026 and guard.fresh_year(date(2027, 3, 31)) == 2026
    assert guard.fresh_year(date(2027, 4, 1)) == 2027


def test_the_newest_year_comes_from_the_cited_facts_and_an_x_post_is_this_weeks():
    assert guard.newest_year(["A1", "A2"], BY, TODAY) == 2026
    assert guard.newest_year(["A2", "A3"], BY, TODAY) == 2025
    assert guard.newest_year(["A3"], BY, TODAY) == 0
    assert guard.newest_year(["A4"], BY, TODAY) == 2026


def test_a_point_with_only_older_data_must_say_it_is_the_latest_available():
    errs = guard.stale_errors(
        [point("A2"), point("A1"), point("A2", body="The latest available data.")], BY, TODAY
    )
    assert (
        len(errs) == 1
        and errs[0].startswith("point 1: its newest figure is from 2025")
        and "2026" in errs[0]
    )


def test_dated_marks_older_points_and_says_so_once():
    assert guard.dated(point("A1"), BY, TODAY).older == ""
    old = guard.dated(point("A2"), BY, TODAY)
    assert (
        old.older == "2025"
        and old.body == "Text. These are the latest figures available, from 2025."
    )
    said = guard.dated(point("A2", body="The latest available data."), BY, TODAY)
    assert said.older == "2025" and said.body == "The latest available data."
    undated = guard.dated(point("A3"), BY, TODAY)
    assert undated.older == "undated" and undated.body.endswith(
        "The sources give no date for these figures."
    )


class FakeEditor:
    def __init__(self, *outs):
        self.outs, self.calls, self.last_usage = list(outs), [], (800, 300)

    def parse(self, *, system, messages, schema):
        self.calls.append(list(messages))
        return self.outs.pop(0), []


def session(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_RESEARCH_DIR", str(tmp_path))
    s = store.create("AI adoption", Clarification(question="How fast?", questions=[]))
    with store.edit(s.id) as x:
        x.agents = [agent("A", facts=[BY["A1"], BY["A2"]])]
    return store.load(s.id)


def draft(fid, body):
    return ReportDraft(
        title="t",
        subtitle="s",
        caveats=[],
        points=[PointDraft(agent="A", headline="h", body=body, fact_ids=[fid])],
    )


def test_the_writer_retries_once_for_older_data_then_keeps_and_marks_it(tmp_path, monkeypatch):
    monkeypatch.setattr(synthesizer, "date", type("D", (), {"today": staticmethod(lambda: TODAY)}))
    ed = FakeEditor(draft("A2", "44.0% in 2025."), draft("A2", "44.0% in 2025."))
    rep = synthesizer.write(session(tmp_path, monkeypatch), llm.Meter(), client=ed)
    assert "its newest figure is from 2025" in ed.calls[1][-1]["content"]
    assert rep.points[0].older == "2025" and rep.points[0].body.endswith(
        "latest figures available, from 2025."
    )


def test_a_fresh_draft_is_not_sent_back(tmp_path, monkeypatch):
    monkeypatch.setattr(synthesizer, "date", type("D", (), {"today": staticmethod(lambda: TODAY)}))
    ed = FakeEditor(draft("A1", "55.9% in Q3 2026."))
    rep = synthesizer.write(session(tmp_path, monkeypatch), llm.Meter(), client=ed)
    assert len(ed.calls) == 1 and rep.points[0].older == ""


def test_the_critic_sees_which_findings_rest_on_older_data(tmp_path, monkeypatch):
    s = session(tmp_path, monkeypatch)
    s.agents[0].findings = [
        Finding(id="f1", claim="Adoption is 44%", fact_ids=["A2"]),
        Finding(id="f2", claim="Now 55.9%", fact_ids=["A1"]),
    ]
    text = critic.findings_text(s, TODAY)
    assert "- Adoption is 44% (newest data: 2025)" in text and "- Now 55.9%\n" in text + "\n"


@pytest.mark.parametrize("module", ["sub_agent", "lead"])
def test_the_agents_are_told_about_the_live_data_tools(module):
    import importlib

    m = importlib.import_module(f"castelino.agents.research.deep.{module}")
    assert "Ramp AI Index" in m.SYSTEM and "OpenRouter" in m.SYSTEM
