import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from castelino.agents.research.deep import publish, runner, store
from castelino.agents.research.deep.models import (
    ChartValue,
    Clarification,
    Point,
    PointChart,
    ResearchReport,
    SubstackDraft,
)
from castelino.dashboard.endpoints import deep_research
from tests.research_fakes import agent, fact


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_RESEARCH_DIR", str(tmp_path))
    monkeypatch.setenv("SUBSTACK_PUBLICATION_URL", "https://pub.example")
    monkeypatch.setenv("SUBSTACK_SID", "sid")


def chart(form, *vals, unit="%"):
    values = [ChartValue(fact_id="A1", label=f"v{i}", value=v) for i, v in enumerate(vals)]
    return PointChart(form=form, title=f"A {form} chart", unit=unit, values=values)


def report_session():
    s = store.create(
        "AI adoption", Clarification(question="How fast are firms adopting AI?", questions=[])
    )
    pts = [
        Point(
            id="p1",
            agent="A",
            headline="AI use reached 9.2% of firms.",
            body="9.2%.",
            fact_ids=["A1"],
            chart=chart("stat", 9.2),
        ),
        Point(
            id="p2",
            agent="A",
            headline="It rose fast.",
            body="From 5% to 9.2%.\n\nWhy it rose.",
            fact_ids=["A1"],
            chart=chart("line", 5, 7, 9.2),
        ),
        Point(
            id="p3",
            agent="A",
            headline="Large firms lead.",
            body="Big gap.",
            fact_ids=["A1"],
            chart=chart("bars", 27, 9.2),
        ),
        Point(
            id="p4",
            agent="A",
            headline="A year on.",
            body="Up.",
            fact_ids=["A1"],
            chart=chart("dumbbell", 5, 9.2),
        ),
        Point(id="p5", agent="A", headline="No figure here.", body="Broad use.", fact_ids=["A1"]),
    ]
    with store.edit(s.id) as x:
        x.agents = [
            agent(
                "A",
                facts=[
                    fact("A1", "AI use reached 9.2% of firms", [9.2], url="https://census.gov/x")
                ],
            )
        ]
        x.report = ResearchReport(
            title="One in ten firms use AI",
            subtitle="US data",
            points=pts,
            caveats=["Survey data."],
        )
        x.status = "complete"
    return s.id


def test_every_charted_point_is_drawn_as_a_png():
    sid = report_session()
    pngs = publish.render(store.load(sid))
    assert sorted(pngs) == ["p1.png", "p2.png", "p3.png", "p4.png"]
    assert all(p.read_bytes()[:4] == b"\x89PNG" for p in pngs.values())


def test_the_draft_has_key_findings_each_point_with_its_chart_and_sources():
    s = store.load(report_session())
    up = {f"p{i}.png": {"url": f"https://img/{i}"} for i in range(1, 5)}
    body = json.dumps(publish.doc(s, up))
    assert "Key findings" in body and "AI use reached 9.2% of firms." in body
    assert body.count("captionedImage") == 4 and "https://img/3" in body
    paras = [n for n in publish.doc(s, up)["content"] if n["type"] == "paragraph"]
    texts = [n["content"][0]["text"] for n in paras if n.get("content")]
    assert "From 5% to 9.2%." in texts and "Why it rose." in texts  # one Substack paragraph each
    assert (
        "https://census.gov/x" in body
        and "Survey data." in body
        and "Not investment advice" in body
    )


@pytest.fixture
def substack(monkeypatch):
    calls = {"push": 0, "section": [], "draft": {"draft_body": "{}"}}

    def push(*, marker, title, subtitle, pngs, body, label, cover=None):
        calls["push"] += 1
        body({n: {"url": n} for n in pngs})
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"draft_id": 42}))
        return "created draft 42"

    monkeypatch.setattr(publish.sb, "push", push)
    monkeypatch.setattr(
        publish, "_set_section", lambda d, section: calls["section"].append((d, section))
    )
    monkeypatch.setattr(publish, "_get", lambda d: calls["draft"])
    return calls


def test_push_makes_the_draft_in_the_ai_section_and_remembers_it(substack):
    sid = report_session()
    publish.push(sid)
    d = store.load(sid).substack
    assert substack["push"] == 1 and substack["section"] == [(42, 466773)]
    assert (
        d.draft_id == 42 and d.url == "https://pub.example/publish/post/42" and d.sha and not d.note
    )


def test_a_draft_edited_on_substack_is_never_overwritten(substack):
    sid = report_session()
    publish.push(sid)
    substack["draft"] = {"draft_body": json.dumps({"content": [{"text": "my own words"}]})}
    publish.push(sid)
    assert substack["push"] == 1 and "edited" in store.load(sid).substack.note


def test_a_failed_push_is_noted_and_never_raises(monkeypatch):
    sid = report_session()
    monkeypatch.setattr(
        publish.sb, "push", lambda **k: (_ for _ in ()).throw(RuntimeError("cookie expired"))
    )
    publish.push(sid)
    assert "cookie expired" in store.load(sid).substack.note


def test_a_finished_run_and_an_addition_push_the_draft(monkeypatch):
    pushed = []
    monkeypatch.setattr(publish, "push", pushed.append)
    sid = report_session()
    monkeypatch.setattr(
        runner, "STEPS", {**runner.STEPS, "run": lambda s, m: None, "add": lambda s, m: None}
    )
    runner._execute(sid, "run")
    runner._execute(sid, "add")
    runner._execute(sid, "charts")
    assert pushed == [sid, sid]


def test_approving_an_edit_and_the_retry_button_redraft_in_the_background(monkeypatch):
    later = []
    monkeypatch.setattr(runner, "draft_later", later.append)
    monkeypatch.setattr(deep_research.editor_desk, "approve", lambda sid, n: None)
    app = FastAPI()
    app.include_router(deep_research.router)
    c = TestClient(app)
    sid = report_session()
    assert c.post(f"/admin/desk/research/{sid}/proposals/1/approve").status_code == 200
    assert c.post(f"/admin/desk/research/{sid}/substack").status_code == 200
    assert later == [sid, sid]


def test_the_draft_link_is_public_to_the_tab():
    sid = report_session()
    with store.edit(sid) as x:
        x.substack = SubstackDraft(
            draft_id=42, url="https://pub.example/publish/post/42", sha="abc", at="x"
        )
    assert deep_research._public(store.load(sid))["substack"]["url"].endswith("/42")
