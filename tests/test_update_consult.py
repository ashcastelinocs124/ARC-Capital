"""The Daily Update consults the topic consultants: the Orchestrator sees what they watch, the Editor
writes an ARC view paragraph under the items they cover, and a bad view is dropped, never fatal."""

from castelino.agents.consultants import consult, store
from castelino.agents.consultants.models import NoteConsult, Part, Thesis, Watchlist
from castelino.agents.update import editor
from castelino.agents.update.models import Briefs, DailyRecordV2, Fact, ItemView
from tests.test_update_runner import DAY, build, make_note

KFACT = Fact(
    id="K1-20261007-1",
    text="Listings were pulled",
    numbers=[41.2],
    provenance="reported",
    source_title="FT",
    source_url="u",
)
NC = NoteConsult(
    watch_md="- AI: leaning to a funding squeeze",
    prompt_md="### AI models and chips (consultant: ai)\nWhat's happening: the squeeze",
    facts=[KFACT],
    codes={"ai": "K1"},
    names={"ai": "AI models and chips"},
)


def with_view(text, fids=("K1-20261007-1",)):
    n = make_note()
    items = list(n.items)
    view = ItemView(consultant="ai", text=text, fact_ids=list(fids))
    items[0] = items[0].model_copy(update={"view": view})
    return n.model_copy(update={"items": items})


def wire(runner, consult_fn=lambda day, d: NC):
    runner.consult_fn = consult_fn
    seen: dict = {"calls": []}

    def editor_fn(findings, facts, mem, long, errors, consultants_md=""):
        seen["calls"].append((facts, consultants_md, errors))
        return seen.get("note") or with_view("Funding is the squeeze; watch cloud budgets.")

    plans: list = []

    def plan_fn(mem, long, today, watch=""):
        plans.append(watch)
        return Briefs(macro="m", news="n", alt="a")

    runner.editor_fn, runner.plan_fn = editor_fn, plan_fn
    return seen, plans


def record(tmp_path) -> DailyRecordV2:
    return DailyRecordV2.model_validate_json((tmp_path / "updates" / f"{DAY}.json").read_text())


def test_editor_gets_consultant_md_and_facts(tmp_path):
    runner, _ = build(tmp_path)
    seen, _ = wire(runner)
    assert runner.run_if_due() == "done"
    facts, md, _ = seen["calls"][0]
    assert "K1-20261007-1" in {f.id for f in facts} and "consultant: ai" in md
    assert record(tmp_path).note.items[0].view.topic == "AI models and chips"


def test_plan_gets_watch_md(tmp_path):
    runner, _ = build(tmp_path)
    _, plans = wire(runner)
    runner.run_if_due()
    assert plans == ["- AI: leaning to a funding squeeze"]


def test_bad_view_is_dropped_and_note_still_written(tmp_path):
    runner, _ = build(tmp_path)
    seen, _ = wire(runner)
    seen["note"] = with_view("Revenue grew 9%, so the squeeze moves to financing.")
    assert runner.run_if_due() == "done"
    r = record(tmp_path)
    assert r.note.items[0].view is None
    assert any("ARC view dropped on item 1" in g for g in r.data_gaps)
    assert len(seen["calls"]) == 2 and any("ARC view" in e for e in seen["calls"][1][2])


def test_consult_fn_failure_is_a_gap(tmp_path):
    runner, _ = build(tmp_path)

    def boom(day, updates_dir):
        raise RuntimeError("store down")

    seen, plans = wire(runner, boom)
    seen["note"] = make_note()
    assert runner.run_if_due() == "done"
    assert any("consultants" in g for g in record(tmp_path).data_gaps)
    assert plans == [""]


def _thesis(text: str, version: int) -> Thesis:
    p = Part(text=text, fact_ids=[])
    return Thesis(
        happening=p, lean=p, alternative=p, change_mind=p, reason="r", updated="x", version=version
    )


def test_rebuild_uses_saved_day_consult(tmp_path):
    c = store.create("AI", Watchlist(companies=[], series=[], queries=[]))
    store.write_thesis(c.slug, _thesis("Funding is the squeeze.", 1))
    runner, _ = build(tmp_path)
    seen, _ = wire(runner, consult.for_note)
    seen["note"] = make_note()
    assert runner.run_if_due() == "done"
    store.write_thesis(c.slug, _thesis("Changed later.", 2))
    runner.rebuild(DAY.isoformat())
    md = seen["calls"][-1][1]
    assert "Funding is the squeeze." in md and "Changed later." not in md


def test_system_prompt_view_rules():
    s = editor.SYSTEM.lower()
    for phrase in (
        "one paragraph",
        "what could happen",
        "do not repeat the item's numbers",
        "no buy or sell",
    ):
        assert phrase in s
