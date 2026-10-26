import json

import pytest
from fastapi.testclient import TestClient

from castelino.agents.update import desk, desk_edit, exhibits
from castelino.agents.update import runner as runner_mod
from castelino.agents.update.models import AgentOutput, Exhibit
from castelino.substack import chart_slots
from tests.test_update_runner import build, make_note, output, record

DAY = "2026-10-07"


@pytest.fixture
def day(tmp_path, monkeypatch):
    """A written day (items 1-3 charted, exhibits 1-3) the desk reads from tmp_path."""
    runner, calls = build(tmp_path)
    runner.run_if_due()
    monkeypatch.setattr(desk, "_dirs", lambda: (tmp_path, tmp_path / "updates"))
    monkeypatch.setattr(runner_mod, "build_default_runner", lambda: runner)
    return runner, calls


def route(kind="change", items=(2,), finding_ids=(), agent="none", brief=""):
    return desk_edit.EditRoute(
        kind=kind,
        items=list(items),
        top=False,
        finding_ids=list(finding_ids),
        agent=agent,
        brief=brief,
        reason="I'll rewrite item 2.",
    )


def routes(monkeypatch, r):
    seen = []

    def fake(self, **kw):
        seen.append(kw)
        return r

    monkeypatch.setattr(desk_edit.EditRouter, "__call__", fake)
    return seen


def editor(runner, body="Shorter: CPI at 3.71%.", first_bad=False, cite=None):
    """An Editor that rewrites item 2 (item 4 rests on `cite`, a new point) and records the
    request it was given on each try."""
    asked = []

    def fn(findings, facts, mem, long, errors, consultants_md="", request_md=""):
        asked.append(request_md)
        note = make_note()
        note.items[1].body = body
        if cite:
            note.items[3].finding_ids = [cite]
        if first_bad and len(asked) == 1:
            note.items[1].body = "Made up 9.99%."
        return note

    runner.editor_fn = fn
    return asked


def test_change_is_a_draft_until_approved(tmp_path, monkeypatch, day):
    runner, _ = day
    seen = routes(monkeypatch, route())
    asked = editor(runner, first_bad=True)
    steps = []
    out = desk_edit.edit(DAY, "Shorten item 2", steps.append)
    assert out["kind"] == "change" and out["message"] == "Item 2 rewritten."
    assert "Item 2: T" in seen[0]["note_md"] and "Shorten item 2" == seen[0]["ask"]
    assert len(asked) == 2 and all('asked: "Shorten item 2"' in a for a in asked)  # every retry
    assert "I'll rewrite item 2." in steps
    assert record(tmp_path).note.items[1].body == "CPI at 3.71%."  # untouched until approved
    prop = desk_edit.proposal(DAY)
    assert prop["note"]["items"][1]["body"] == "Shorter: CPI at 3.71%."
    assert desk_edit.approve(DAY) == "Item 2 rewritten."
    assert record(tmp_path).note.items[1].body == "Shorter: CPI at 3.71%."
    assert desk_edit.proposal(DAY) is None
    assert list((tmp_path / "updates").glob("hidden-rebuild-*/2026-10-07.json"))


def test_new_point_gets_a_mini_run_first(tmp_path, monkeypatch, day):
    runner, _ = day
    routes(monkeypatch, route("new", (), (), "ai", "Find the chip deal on 2026-10-07."))
    asked = editor(runner, cite="ai-1")
    ran = []

    def ai_run(brief, ask, **kw):
        ran.append(ask)
        return output("ai", n=1)

    monkeypatch.setattr(desk, "_run_fn", lambda agent: ai_run)
    out = desk_edit.edit(DAY, "Add the chip deal", lambda s: None)
    assert ran == ["Find the chip deal on 2026-10-07."]
    assert out["agent"] == "ai" and out["added"] == ["ai-1"]
    assert "resting on findings ai-1" in asked[0]
    assert any(f.id == "ai-1" for f in record(tmp_path).findings)  # merged, as Re-run does


def test_new_point_nothing_found_makes_no_draft(monkeypatch, day):
    routes(monkeypatch, route("new", (), (), "news", "x"))
    monkeypatch.setattr(
        desk, "_run_fn", lambda agent: lambda b, a, **k: AgentOutput(facts=[], findings=[])
    )
    out = desk_edit.edit(DAY, "Add a rumour", lambda s: None)
    assert out["kind"] == "none" and "found nothing" in out["message"]
    assert desk_edit.proposal(DAY) is None


def test_new_point_the_findings_cover_skips_research(monkeypatch, day):
    runner, _ = day
    routes(monkeypatch, route("new", (), ("news-2", "made-up-9"), "news", "x"))
    asked = editor(runner)
    monkeypatch.setattr(desk, "_run_fn", lambda agent: pytest.fail("no research needed"))
    desk_edit.edit(DAY, "Add the second news story", lambda s: None)
    assert "resting on findings news-2." in asked[0]


def test_a_stale_draft_is_refused_and_reject_drops_it(tmp_path, monkeypatch, day):
    runner, _ = day
    routes(monkeypatch, route())
    editor(runner)
    desk_edit.edit(DAY, "Shorten item 2", lambda s: None)
    rec = record(tmp_path)
    (tmp_path / "updates" / f"{DAY}.json").write_text(
        rec.model_copy(update={"data_gaps": ["a re-run"]}).model_dump_json(indent=2)
    )
    with pytest.raises(desk_edit.StaleProposalError):
        desk_edit.approve(DAY)
    desk_edit.reject(DAY)
    assert desk_edit.proposal(DAY) is None


def hand(rec, **kw):
    return desk_edit.HandEdit(
        headline=rec.note.headline,
        takeaways=rec.note.takeaways,
        items=[
            desk_edit.HandItem(rank=it.rank, title=it.title, body=it.body) for it in rec.note.items
        ],
        **kw,
    )


def test_hand_edit_warns_on_new_figures_and_saves_bold(tmp_path, day):
    rec = record(tmp_path)
    e = hand(rec)
    e.items[0].body = "CPI at **3.71%**, and 9.99% more."
    warnings = desk_edit.check_hand_edit(DAY, e)
    assert len(warnings) == 1 and "9.99" in warnings[0]
    assert desk_edit.save_hand_edit(DAY, e) == "Saved your edits"
    saved = record(tmp_path)
    assert saved.note.items[0].body == "CPI at **3.71%**, and 9.99% more."
    assert saved.hand_edited_at


def test_hand_edit_refuses_a_changed_shape(tmp_path, day):
    e = hand(record(tmp_path))
    e.items.pop()
    with pytest.raises(ValueError, match="reload"):
        desk_edit.save_hand_edit(DAY, e)


def test_moving_a_chart_renumbers_in_reading_order(tmp_path, monkeypatch, day):
    drawn = []

    def fake_charts(note, findings, facts, out_dir, order=None):
        drawn.append(order)
        return [
            Exhibit(
                n=n,
                finding_id="f",
                item=r,
                title=f"Exhibit {n}",
                subtitle="",
                file=f"exhibit_{n}.png",
            )
            for n, r in enumerate(order, 1)
        ]

    monkeypatch.setattr(exhibits, "make_note_exhibits", fake_charts)
    rec = record(tmp_path)  # item r has exhibit r, for r = 1..3
    e = hand(rec, charts=[desk_edit.ChartPlace(file="exhibit_3.png", at=1, after=0)])
    assert "renumbered" in desk_edit.save_hand_edit(DAY, e)
    assert drawn == [[3, 1, 2]]  # item 3's chart now leads item 1
    saved = record(tmp_path)
    first = saved.exhibits[0]
    assert (first.n, first.item, first.at, first.after) == (1, 3, 1, 0)
    # a move inside an item that keeps the order redraws nothing
    e = hand(saved, charts=[desk_edit.ChartPlace(file="exhibit_2.png", at=1, after=None)])
    assert desk_edit.save_hand_edit(DAY, e) == "Saved your edits" and len(drawn) == 1


def test_chart_slots_follow_the_desk():
    ex = [
        {"n": 1, "item": 1, "file": "a"},
        {"n": 2, "item": 2, "at": 1, "after": 0, "file": "b"},
        {"n": 3, "item": 3, "after": 9, "file": "c"},
    ]
    assert chart_slots(1, 4, ex) == {4: [ex[0]], 0: [ex[1]]}
    assert chart_slots(2, 4, ex) == {}
    assert chart_slots(3, 4, ex) == {4: [ex[2]]}  # past the end = after the last paragraph


def test_rebuild_drops_the_hand_edit_mark(tmp_path, day):
    runner, _ = day
    desk_edit.save_hand_edit(DAY, hand(record(tmp_path)))
    assert record(tmp_path).hand_edited_at
    runner.rebuild(DAY)
    assert record(tmp_path).hand_edited_at is None


class _Inline:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


def test_desk_api_edit_steps_draft_and_approve(tmp_path, monkeypatch, day):
    from castelino.dashboard.endpoints import admin_desk
    from castelino.dashboard.main import app

    runner, _ = day
    routes(monkeypatch, route())
    editor(runner)
    monkeypatch.setattr(admin_desk.threading, "Thread", _Inline)
    monkeypatch.setattr(admin_desk, "_jobs", {})
    c = TestClient(app)
    job = c.post(f"/admin/desk/{DAY}/edit", json={"ask": "Shorten item 2"}).json()
    assert job["state"] == "done" and job["result"]["kind"] == "change", job
    assert job["steps"][0].startswith("Reading your request")
    d = c.get(f"/admin/desk/{DAY}").json()
    assert (
        d["proposal"]["summary"]["changed"] == [2] and d["exhibits"][0]["file"] == "exhibit_1.png"
    )
    assert c.post(f"/admin/desk/{DAY}/edit/approve").json() == {"message": "Item 2 rewritten."}
    assert c.post(f"/admin/desk/{DAY}/edit/approve").status_code == 404
    e = hand(record(tmp_path))
    e.items[0].body = "Up 9.99%."
    r = c.post(f"/admin/desk/{DAY}/note/check", json={"edit": json.loads(e.model_dump_json())})
    assert len(r.json()["warnings"]) == 1
    e.items.pop()
    r = c.post(f"/admin/desk/{DAY}/note", json={"edit": json.loads(e.model_dump_json())})
    assert r.status_code == 400


def test_what_the_request_is_not_about_comes_back_word_for_word(tmp_path, monkeypatch, day):
    """The Editor rewords items it was told to keep; the desk puts them back."""
    runner, _ = day
    routes(monkeypatch, route(items=(2,)))
    asked = editor(runner)
    inner = runner.editor_fn

    def wordy(*a, **k):
        note = inner(*a, **k)
        note.items[3].body = "Reworded without being asked: CPI at 3.71%."
        note.headline = "A new headline nobody asked for at 3.71%"
        return note

    runner.editor_fn = wordy
    out = desk_edit.edit(DAY, "Shorten item 2", lambda s: None)
    note = desk_edit.proposal(DAY)["note"]
    assert note["items"][1]["body"] == "Shorter: CPI at 3.71%."
    assert note["items"][3]["body"] == "CPI at 3.71%." and note["headline"] == "Inflation at 3.71%"
    assert out["summary"]["changed"] == [2] and asked


def test_a_new_point_keeps_the_other_items_and_moves_them_down(day):
    old = make_note(fids=("macro-1", "news-1", "alt-1"))
    for i, it in enumerate(old.items):
        it.title, it.body = f"Story {i + 1}", f"Body {i + 1}"
    new = old.model_copy(deep=True)
    new.items = [new.items[0], new.items[1], new.items[2], new.items[3]]
    for it in new.items:
        it.body = "Reworded"
    point = new.items[0].model_copy(
        update={"title": "The new point", "body": "Fresh", "finding_ids": ["ai-1"]}
    )
    new.items = [new.items[0], point, *new.items[1:]]
    for r, it in enumerate(new.items, 1):
        it.rank = r
    merged = desk_edit.keep_untouched(old, route("new", ()), ["ai-1"])(new)
    assert [(it.rank, it.title, it.body) for it in merged.items] == [
        (1, "Story 1", "Body 1"),
        (2, "The new point", "Fresh"),
        (3, "Story 2", "Body 2"),
        (4, "Story 3", "Body 3"),
        (5, "Story 4", "Body 4"),
    ]


def test_a_figure_typed_by_hand_does_not_block_a_later_edit(tmp_path, monkeypatch, day):
    runner, _ = day
    e = hand(record(tmp_path))
    e.items[0].body = "Typed by hand: 9.99%."
    desk_edit.save_hand_edit(DAY, e)  # accepted with its warning
    routes(monkeypatch, route(items=(2,)))
    editor(runner)
    desk_edit.edit(DAY, "Shorten item 2", lambda s: None)
    note = desk_edit.proposal(DAY)["note"]
    assert note["items"][0]["body"] == "Typed by hand: 9.99%."  # kept, and the guard let it pass


def test_an_edit_keeps_the_days_saved_context_facts(monkeypatch, day):
    """Recomputed prices would no longer match the note's figures, so an edit reuses them."""
    runner, _ = day
    runner.background_fn = lambda *a: pytest.fail("an edit must not recompute the background")
    runner.calendar_fn = lambda *a: pytest.fail("nor the calendar")
    runner.sentiment_fn = lambda *a: pytest.fail("nor the sentiment facts")
    routes(monkeypatch, route())
    editor(runner)
    assert desk_edit.edit(DAY, "Shorten item 2", lambda s: None)["kind"] == "change"
