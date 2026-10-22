from datetime import date

import pytest

from castelino.agents.consultants import build, review, store
from castelino.agents.consultants import runner as crunner
from castelino.agents.consultants.models import Watchlist
from castelino.agents.update.models import DailyRecordV2, MorningNote
from castelino.dashboard.endpoints import refresh as ep

WL = Watchlist(companies=[], series=[], queries=["q"])
SUNDAY, MONDAY = date(2026, 10, 18), date(2026, 10, 19)


def record(updates_dir, day: date) -> None:
    note = MorningNote(headline="H", takeaways=[], items=[], themes_touched=[], new_themes=[])
    rec = DailyRecordV2(
        date=day.isoformat(),
        generated_at="x",
        findings=[],
        note=note,
        exhibits=[],
        releases=[],
        rounds=0,
        data_gaps=[],
    )
    updates_dir.mkdir(parents=True, exist_ok=True)
    (updates_dir / f"{day}.json").write_text(rec.model_dump_json())


@pytest.fixture
def calls(monkeypatch):
    seen: list = []
    monkeypatch.setattr(build, "build", lambda slug, day, m: seen.append(("build", slug)) or [])
    monkeypatch.setattr(
        review, "daily", lambda slug, day, findings, m: seen.append(("daily", slug, day))
    )
    monkeypatch.setattr(
        review, "weekly", lambda slug, we, m: seen.append(("weekly", slug, we.isoformat()))
    )
    return seen


def test_before_note_builds_active_not_paused(calls):
    a = store.create("AI", WL)
    b = store.create("India", WL)
    with store.edit(b.slug) as x:
        x.status = "paused"
    crunner.before_note(MONDAY)
    assert calls == [("build", a.slug)]


def test_build_failure_does_not_raise(monkeypatch):
    c = store.create("AI", WL)

    def boom(slug, day, m):
        raise RuntimeError("model down")

    monkeypatch.setattr(build, "build", boom)
    assert crunner.before_note(MONDAY) == []
    assert "build failed" in store.day_log(c.slug, MONDAY.isoformat()).notes[0]


def test_cap_skips_step_and_logs_note(calls):
    c = store.create("AI", WL)
    with store.edit_day(c.slug, MONDAY.isoformat()) as d:
        d.cost_usd = 0.95
    crunner.before_note(MONDAY)
    assert calls == []
    assert "cost cap" in store.day_log(c.slug, MONDAY.isoformat()).notes[0]


def test_after_note_order_on_sunday(calls, tmp_path):
    c = store.create("AI", WL)
    record(tmp_path / "updates", SUNDAY)
    crunner.after_note(SUNDAY, tmp_path / "updates")
    assert calls == [("daily", c.slug, "2026-10-18"), ("weekly", c.slug, "2026-10-18")]


def test_after_note_catch_up_on_monday(calls, tmp_path):
    c = store.create("AI", WL)
    record(tmp_path / "updates", MONDAY)
    crunner.after_note(MONDAY, tmp_path / "updates")
    assert calls == [("weekly", c.slug, "2026-10-18"), ("daily", c.slug, "2026-10-19")]


def test_after_note_without_note_logs_skipped_and_still_catches_up(calls, tmp_path):
    c = store.create("AI", WL)
    crunner.after_note(MONDAY, tmp_path / "updates")
    crunner.after_note(MONDAY, tmp_path / "updates")
    assert calls == [("weekly", c.slug, "2026-10-18")] * 2
    skipped = [h for h in store.history(c.slug) if h.verdict == "skipped"]
    assert len(skipped) == 1 and skipped[0].reason == "No Daily Update today."


def test_job_update_agent_calls_before_and_after_even_when_skipped(monkeypatch):
    hooks: list = []

    class FakeRunner:
        def run_if_due(self):
            hooks.append("note")
            return "skipped"

    monkeypatch.setattr("castelino.agents.update.runner.build_default_runner", lambda: FakeRunner())
    monkeypatch.setattr(crunner, "before_note", lambda day: hooks.append("before") or [])
    monkeypatch.setattr(crunner, "after_note", lambda day, d: hooks.append("after"))
    with pytest.raises(ep.Skipped):
        ep.job_update_agent()
    assert hooks == ["before", "note", "after"]
