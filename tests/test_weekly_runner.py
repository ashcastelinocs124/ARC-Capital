import json
from datetime import date

from castelino.agents.weekly.models import (
    AgentRun,
    Bullet,
    Challenge,
    DeepPlan,
    ExhibitPick,
    Grill,
    GrillExchange,
    GrillQuestion,
    RegimeRead,
    SubAgentSpec,
    Trend,
    TrendSection,
    WeeklyFinding,
    WeeklyRecord,
    WeeklyReport,
)
from castelino.agents.weekly.runner import WeeklyRunner
from tests.weekly_fixtures import fact

SUN = date(2026, 10, 11)
DAYS = ("2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09")


def notes(d, days=DAYS):
    d.mkdir(parents=True, exist_ok=True)
    for day in days:
        rec = {
            "version": 2,
            "date": day,
            "findings": [],
            "note": {"headline": f"H {day}", "takeaways": ["t"], "items": []},
        }
        (d / f"{day}.json").write_text(json.dumps(rec))


def spec(name, trends=()):
    return SubAgentSpec(
        name=name,
        description="d",
        goal="g",
        tools=["fred_series"],
        related=[],
        trends=list(trends),
    )


DESKS = ["Rates desk", "Chips desk", "Energy desk", "Breadth desk", "Broken desk"]
PLAN = DeepPlan(
    trends=[Trend(title=f"t{i}", why="w") for i in range(10)],
    agents=[spec(n, [f"t{2 * k}", f"t{2 * k + 1}"]) for k, n in enumerate(DESKS)],
)


class FakeBox:
    def __init__(self, prefix):
        self.facts = [fact(f"{prefix}1", nums=(28, 4.38))]
        self.calls = 3


class FakeSession:
    def __init__(self, spec, prefix, board, end):
        self.name, self.prefix, self.board = spec.name, prefix, board
        self.toolbox = FakeBox(prefix)

    def run(self, brief):
        if self.name == "Broken desk":
            raise RuntimeError("timeout")
        f = self.toolbox.facts[0]
        if self.prefix == "A":
            self.board.post(self.name, "10y up 28bp", [f])
        finding = WeeklyFinding(
            id=f"{self.prefix}-f1",
            agent=self.name,
            claim="c",
            provenance="data",
            source_title="s",
            source_url="u",
            fact_ids=[f.id],
        )
        return AgentRun(
            agent=self.name, facts=list(self.toolbox.facts), tool_calls=3, findings=[finding]
        )

    def answer(self, q):
        return GrillExchange(
            agent=self.name,
            finding_id=q.finding_id,
            question=q.question,
            answer="Yes, 28bp.",
            fact_ids=[],
        )


def sec(title, ids, para):
    return TrendSection(
        title=title,
        agent="Rates desk",
        paragraphs=[para],
        fact_ids=ids,
        exhibits=[ExhibitPick(fact_id=ids[0], window_days=90)],
        challenges=[Challenge(question="q", answer="Yes, 28bp.", verdict="Accepted")],
    )


def report(paragraph="Chips rallied even as the 10y rose 28bp."):
    # section 2 cites the Rates desk's fact A1 that the Chips desk read from the board;
    # a weekly has 10-12 trend sections, so 8 more fill it out
    sections = [
        sec("Long end", ["A1"], "The 10y rose 28bp."),
        sec("Chips", ["B1", "A1"], paragraph),
        *(sec(f"Trend {i}", ["C1"], "Up 28bp.") for i in range(3, 11)),
    ]
    return WeeklyReport(
        title="Yields up",
        subtitle="s",
        watch="CPI.",
        bullets=[Bullet(lead="Up 28bp.", body="b", fact_ids=["A1"]) for _ in sections],
        sections=sections,
    )


class FakeEditor:
    def __init__(self, reports):
        self.reports, self.grills = list(reports), []

    def open(self, desk_md):
        assert "## Desk: Rates desk" in desk_md and "## Desk: Broken desk" not in desk_md
        return Grill(
            done=False,
            questions=[
                GrillQuestion(agent="Rates desk", finding_id="A-f1", question="Growth?"),
                GrillQuestion(agent="Broken desk", finding_id="x", question="skipped"),
                GrillQuestion(agent="Ghost desk", finding_id="y", question="skipped"),
            ],
        )

    def followup(self, answers_md, last):
        self.grills.append(answers_md)
        return Grill(done=True, questions=[])

    def write(self, errors):
        return self.reports.pop(0)


def runner(tmp_path, editor, plan_fn=lambda w, md, mem: PLAN, preflight=lambda: None):
    notes(tmp_path / "updates")
    return WeeklyRunner(
        deep_dir=tmp_path / "deep",
        updates_dir=tmp_path / "updates",
        memory_md_fn=lambda: "",
        plan_fn=plan_fn,
        session_fn=FakeSession,
        editor_fn=lambda: editor,
        chart_fn=lambda rep, facts, out: [],
        scorecard_fn=lambda end: [],
        regime_fn=lambda: RegimeRead(pulse=64, pressure=38),
        today_fn=lambda: SUN,
        preflight_fn=preflight,
        min_notes=3,
        max_grill_rounds=2,
        max_guard_retries=1,
        models={"lead": "gpt-6-sol", "agents": "gpt-6-luna", "editor": "claude-opus-5-5"},
    )


def test_full_run_writes_record_last_with_gaps_and_board_facts(tmp_path):
    r = runner(tmp_path, FakeEditor([report()]))
    assert r.run_if_due() == "done"
    rec = WeeklyRecord.model_validate_json((tmp_path / "deep" / "2026-W41.json").read_text())
    assert rec.week == "2026-W41" and rec.start == "2026-10-05" and rec.end == "2026-10-09"
    assert any("Broken desk agent failed" in g for g in rec.data_gaps)
    assert [g.agent for g in rec.grill_log] == ["Rates desk"]  # failed/unknown desks skipped
    # five desks staffed (prefixes A-E); the fifth, Broken desk, failed
    assert rec.counts.agents == 4 and rec.counts.board_posts == 1
    assert len(rec.report.sections) == 10
    assert rec.counts.grill_rounds == 1
    assert rec.counts.figures_checked >= 4 and rec.regime.pulse == 64
    assert json.loads((tmp_path / "deep" / "status.json").read_text())["stage"] == "done"
    assert (tmp_path / "deep" / "raw" / "2026-W41.json").exists()


def test_second_run_same_week_is_skipped(tmp_path):
    r = runner(tmp_path, FakeEditor([report()]))
    assert r.run_if_due() == "done"
    assert r.run_if_due() == "skipped"


def test_guard_failure_after_retry_fails_and_writes_no_record(tmp_path):
    bad = report("Chips rose 99bp.")
    r = runner(tmp_path, FakeEditor([bad, bad]))
    assert r.run_if_due() == "failed"
    assert not (tmp_path / "deep" / "2026-W41.json").exists()
    st = json.loads((tmp_path / "deep" / "status.json").read_text())
    assert st["stage"] == "failed" and "99bp" in st["error"]


def test_holiday_week_fails_cleanly(tmp_path):
    r = runner(tmp_path, FakeEditor([report()]))
    for p in (tmp_path / "updates").glob("2026-10-0[789].json"):
        p.unlink()
    assert r.run_if_due() == "failed"
    status = json.loads((tmp_path / "deep" / "status.json").read_text())
    assert "only 2 Morning Notes" in status["error"]


def test_editor_preflight_failure_stops_before_any_openai_spend(tmp_path):
    calls = []

    def plan_fn(w, md, mem):
        calls.append("plan")
        return PLAN

    def preflight():
        raise RuntimeError("Your credit balance is too low to access the Anthropic API")

    r = runner(tmp_path, FakeEditor([report()]), plan_fn=plan_fn, preflight=preflight)
    assert r.run_if_due() == "failed"
    assert calls == []  # the Lead (and so every desk) never ran
    status = json.loads((tmp_path / "deep" / "status.json").read_text())
    assert "credit balance" in status["error"]


class CaseEditor(FakeEditor):
    def open(self, desk_md):
        q = GrillQuestion(agent="rates DESK", finding_id="A-f1", question="Growth?")
        return Grill(done=False, questions=[q])


def test_grill_question_routed_despite_desk_name_case(tmp_path):
    r = runner(tmp_path, CaseEditor([report()]))
    assert r.run_if_due() == "done"
    rec = WeeklyRecord.model_validate_json((tmp_path / "deep" / "2026-W41.json").read_text())
    assert [g.agent for g in rec.grill_log] == ["Rates desk"] and rec.counts.grill_rounds == 1
