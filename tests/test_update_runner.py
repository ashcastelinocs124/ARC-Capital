import json
import os
import time
from datetime import date

from castelino.agents.update.memory import MemoryStore
from castelino.agents.update.models import (
    AgentOutput,
    Briefs,
    DailyRecordV2,
    Exhibit,
    Fact,
    Finding,
    FollowUp,
    MarketSnapshot,
    MorningNote,
    NewTheme,
    NoteItem,
    Release,
    Review,
    SeriesRef,
    Stage,
)
from castelino.agents.update.runner import UpdateRunner, read_status

DAY = date(2026, 10, 7)
REF = SeriesRef(kind="daily", provider="fred", id="DGS10", label="10y")


def output(agent, n=2, num=3.71):
    facts = [
        Fact(
            id=f"{agent[0].upper()}{i}",
            text=f"{agent} fact {i}: {num}%",
            numbers=[num],
            provenance="data",
            series=REF,
            source_title="s",
            source_url="u",
        )
        for i in range(1, n + 1)
    ]
    finds = [
        Finding(
            id=f"{agent}-{i}",
            agent=agent,
            claim=f"{agent} claim {i}",
            provenance="data",
            series=REF,
            source_title="s",
            source_url="u",
            fact_ids=[f.id],
        )
        for i, f in enumerate(facts, 1)
    ]
    snap = None
    if agent == "macro":
        snap = MarketSnapshot(
            date="2026-10-07", releases=[Release(series="CPIAUCSL", name="CPI y/y", latest=3.71)]
        )
    return AgentOutput(facts=facts, findings=finds, snapshot=snap)


def make_note(fids=("macro-1", "news-1", "alt-1"), body="CPI at 3.71%.", chart=True):
    items = [
        NoteItem(rank=i, title="T", body=body, finding_ids=[f], chart=f if chart else None)
        for i, f in enumerate(fids, 1)
    ]
    # pad to the required 5 with uncharted items on the first finding
    items += [
        NoteItem(rank=i, title="T", body=body, finding_ids=[fids[0]], chart=None)
        for i in range(len(items) + 1, 6)
    ]
    return MorningNote(
        headline="Inflation at 3.71%",
        takeaways=["a", "b", "c"],
        items=items,
        themes_touched=[],
        new_themes=[NewTheme(title="Sticky CPI", text="t", importance=3)],
    )


class Calls:
    def __init__(self):
        self.agents, self.editor, self.reviews, self.charts = [], [], 0, None


def build(tmp_path, *, agents=None, review=None, editor=None, max_rounds=2):
    calls = Calls()

    def agent_fn(name):
        def fn(brief, ask):
            calls.agents.append((name, ask))
            return output(name)

        return fn

    def review_fn(findings, round_no):
        calls.reviews += 1
        return review(round_no) if review else Review(done=True, followups=[])

    def editor_fn(findings, facts, mem, long, errors):
        calls.editor.append(errors)
        return editor(len(calls.editor)) if editor else make_note()

    def chart_fn(note, findings, facts, out_dir):
        ranked = sorted(note.items, key=lambda i: i.rank)
        calls.charts = [it.chart for it in ranked if it.chart]
        return [
            Exhibit(n=i, finding_id=c, item=r, title="t", subtitle="s", file=f"exhibit_{i}.png")
            for i, (r, c) in enumerate(((it.rank, it.chart) for it in ranked if it.chart), 1)
        ]

    runner = UpdateRunner(
        data_dir=tmp_path,
        updates_dir=tmp_path / "updates",
        memory=MemoryStore(tmp_path / "memory"),
        max_rounds=max_rounds,
        max_retries=1,
        max_items=5,
        plan_fn=lambda mem, long, today: Briefs(macro="m", news="n", alt="a"),
        review_fn=review_fn,
        agent_fns=agents or {a: agent_fn(a) for a in ("macro", "news", "alt")},
        editor_fn=editor_fn,
        chart_fn=chart_fn,
        today_fn=lambda: DAY,
    )
    return runner, calls


def record(root):
    return DailyRecordV2.model_validate_json((root / "updates" / "2026-10-07.json").read_text())


def boom(brief, ask):
    raise RuntimeError("down")


def test_happy_path_writes_record_raw_facts_and_memory(tmp_path):
    runner, calls = build(tmp_path)
    assert runner.run_if_due() == "done"
    rec = record(tmp_path)
    assert rec.version == 2 and len(rec.findings) == 6 and rec.rounds == 0
    assert [e.finding_id for e in rec.exhibits] == ["macro-1", "news-1", "alt-1"] == calls.charts
    assert rec.releases[0].name == "CPI y/y"
    raw = json.loads((tmp_path / "updates" / "raw" / "2026-10-07.json").read_text())
    assert {f["id"] for f in raw} >= {"M1", "N1", "A1"}
    assert "Sticky CPI" in (tmp_path / "memory" / "MEMORY.md").read_text()
    assert read_status(tmp_path)["stage"] == Stage.DONE


def test_second_run_same_day_is_skipped(tmp_path):
    runner, _ = build(tmp_path)
    runner.run_if_due()
    assert runner.run_if_due() == "skipped"


def test_followups_rerun_only_asked_agents_and_stop_at_max_rounds(tmp_path):
    runner, calls = build(
        tmp_path,
        review=lambda r: Review(done=False, followups=[FollowUp(agent="news", ask=f"r{r}")]),
    )
    assert runner.run_if_due() == "done"
    assert calls.reviews == 2 and record(tmp_path).rounds == 2
    assert [c for c in calls.agents if c[1]] == [("news", "r0"), ("news", "r1")]


def test_failed_followup_keeps_first_output_and_notes_gap(tmp_path):
    def flaky(brief, ask):
        if ask:
            raise RuntimeError("timeout")
        return output("news")

    runner, _ = build(
        tmp_path,
        max_rounds=1,
        review=lambda r: Review(done=False, followups=[FollowUp(agent="news", ask="more")]),
        agents={
            "macro": lambda b, a: output("macro"),
            "news": flaky,
            "alt": lambda b, a: output("alt"),
        },
    )
    assert runner.run_if_due() == "done"
    rec = record(tmp_path)
    assert any(f.id == "news-1" for f in rec.findings)
    assert any("news agent failed" in g for g in rec.data_gaps)


def test_one_agent_failing_is_a_gap(tmp_path):
    runner, _ = build(
        tmp_path,
        agents={
            "macro": lambda b, a: output("macro"),
            "news": boom,
            "alt": lambda b, a: output("alt"),
        },
        editor=lambda n: make_note(fids=("macro-1", "macro-2", "alt-1"), chart=False),
    )
    assert runner.run_if_due() == "done"
    assert any("news agent failed" in g for g in record(tmp_path).data_gaps)


def test_all_agents_failing_is_a_failure(tmp_path):
    runner, _ = build(tmp_path, agents={a: boom for a in ("macro", "news", "alt")})
    assert runner.run_if_due() == "failed"
    assert not (tmp_path / "updates" / "2026-10-07.json").exists()
    assert "all research agents failed" in read_status(tmp_path)["error"]


def test_guard_retry_then_success(tmp_path):
    runner, calls = build(
        tmp_path, editor=lambda n: make_note(body="CPI at 9.9%.") if n == 1 else make_note()
    )
    assert runner.run_if_due() == "done"
    assert calls.editor[0] is None and "item 1: 9.9%" in calls.editor[1]


def test_guard_fails_twice_leaves_no_record_and_no_memory(tmp_path):
    runner, _ = build(tmp_path, editor=lambda n: make_note(body="CPI at 9.9%."))
    assert runner.run_if_due() == "failed"
    assert not (tmp_path / "updates" / "2026-10-07.json").exists()
    assert not (tmp_path / "memory" / "MEMORY.md").exists()
    assert "guard failed" in read_status(tmp_path)["error"]


def test_review_error_is_treated_as_done(tmp_path):
    def bad(r):
        raise RuntimeError("llm down")

    runner, _ = build(tmp_path, review=bad)
    assert runner.run_if_due() == "done" and record(tmp_path).rounds == 0


def test_stale_lock_is_cleared(tmp_path):
    lock = tmp_path / "run.lock"
    lock.write_text("999999")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    runner, _ = build(tmp_path)
    assert runner.run_if_due() == "done"


def test_lock_held_by_live_process_blocks(tmp_path):
    (tmp_path / "run.lock").write_text(str(os.getpid()))
    runner, _ = build(tmp_path)
    assert runner.run_if_due() == "locked"


def test_status_defaults_to_idle_when_missing_or_corrupt(tmp_path):
    assert read_status(tmp_path)["stage"] == "idle"
    (tmp_path / "status.json").write_text("{bad")
    assert read_status(tmp_path)["stage"] == "idle"
