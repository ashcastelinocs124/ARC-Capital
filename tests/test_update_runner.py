import os
import time
from datetime import date

from castelino.agents.update.memory import MemoryStore
from castelino.agents.update.models import DailyRecord, Stage
from castelino.agents.update.registry import ModelRegistry
from castelino.agents.update.runner import UpdateRunner, read_status
from tests.update_fixtures import make_forecast, make_snapshot, make_update

DAY = date(2026, 9, 30)


def grounded_update():
    # make_update() cites 76%/87%, which only exist in the snapshot when a champion was seeded
    upd = make_update()
    upd.predictions_changed = "Predictions updated; see the table."
    return upd


class Calls:
    def __init__(self):
        self.agent = []
        self.refits = 0


def build(tmp_path, *, refit=None, agent=None, latest=None, calls=None, seed_champion=False):
    calls = calls or Calls()
    reg = ModelRegistry(tmp_path / "models")
    if seed_champion:
        v = reg.save_version(make_forecast(g_prob=0.76, g_brier=0.236, i_prob=0.87, i_brier=0.189,
                                           feature_month="2026-07-01"))
        reg.set_pointer("growth", v)
        reg.set_pointer("inflation", v)

    def default_refit():
        calls.refits += 1
        return make_forecast(g_prob=0.71, g_brier=0.231, i_prob=0.91, i_brier=0.214)

    def default_agent(snapshot, mem, long, errors):
        calls.agent.append(errors)
        return grounded_update()

    runner = UpdateRunner(
        data_dir=tmp_path, updates_dir=tmp_path / "updates", registry=reg,
        memory=MemoryStore(tmp_path / "memory"), tolerance=0.02, max_retries=1,
        refit_fn=refit or default_refit,
        latest_month_fn=latest or (lambda: {"growth": "2026-08", "inflation": "2026-08"}),
        collect_fn=lambda *, today, prediction, model_note: make_snapshot().model_copy(
            update={"date": today, "prediction": prediction, "model_note": model_note}),
        agent_fn=agent or default_agent,
        today_fn=lambda: DAY,
    )
    return runner, reg, calls


def briefing(tmp_path):
    return tmp_path / "updates" / "2026-09-30.json"


def test_happy_path_writes_everything(tmp_path):
    runner, reg, calls = build(tmp_path, seed_champion=True)
    assert runner.run_if_due() == "done"
    rec = DailyRecord.model_validate_json(briefing(tmp_path).read_text())
    assert rec.date == "2026-09-30" and rec.gate.growth.decision.value == "promoted"
    assert rec.gate.inflation.decision.value == "kept"          # 0.214 vs 0.189 > 0.02
    assert reg.current().growth.prob_up == 0.71 and reg.current().inflation.prob_up == 0.87
    assert rec.snapshot.prediction["growth"].old == 0.76 and rec.snapshot.prediction["growth"].new == 0.71
    assert (tmp_path / "memory" / "MEMORY.md").is_file()
    assert read_status(tmp_path)["stage"] == Stage.DONE.value


def test_second_run_same_day_is_skipped(tmp_path):
    runner, _reg, calls = build(tmp_path)
    assert runner.run_if_due() == "done"
    assert runner.run_if_due() == "skipped"
    assert len(calls.agent) == 1


def test_no_new_data_skips_refit_and_reuses_champion(tmp_path):
    runner, reg, calls = build(
        tmp_path, seed_champion=True,
        latest=lambda: {"growth": "2026-07", "inflation": "2026-07"})
    assert runner.run_if_due() == "done"
    assert calls.refits == 0 and reg.current().growth.prob_up == 0.76


def test_first_ever_run_has_no_champion_and_promotes(tmp_path):
    runner, reg, _ = build(tmp_path)
    assert runner.run_if_due() == "done"
    assert reg.current() is not None


def test_refit_crash_keeps_champion_and_still_ships_briefing(tmp_path):
    def boom():
        raise RuntimeError("xgboost exploded")
    runner, reg, _ = build(tmp_path, refit=boom, seed_champion=True)
    assert runner.run_if_due() == "done"
    rec = DailyRecord.model_validate_json(briefing(tmp_path).read_text())
    assert "not refreshed" in rec.snapshot.model_note and "xgboost exploded" in rec.snapshot.model_note
    assert reg.current().growth.prob_up == 0.76


def test_guard_retry_then_success(tmp_path):
    drafts = []

    def agent(snapshot, mem, long, errors):
        drafts.append(errors)
        upd = grounded_update()
        if errors is None:
            upd.asset_classes = "2y +17bp."
        return upd

    runner, _reg, _ = build(tmp_path, agent=agent)
    assert runner.run_if_due() == "done"
    assert drafts == [None, ["+17bp"]]


def test_guard_fails_twice_leaves_no_briefing_and_no_memory(tmp_path):
    def agent(snapshot, mem, long, errors):
        upd = grounded_update()
        upd.asset_classes = "2y +17bp."
        return upd

    runner, _reg, _ = build(tmp_path, agent=agent)
    assert runner.run_if_due() == "failed"
    assert not briefing(tmp_path).exists()
    assert not (tmp_path / "memory" / "MEMORY.md").exists()
    st = read_status(tmp_path)
    assert st["stage"] == "failed" and "+17bp" in st["error"]


def test_failed_run_is_retried_on_next_call(tmp_path):
    state = {"fail": True}

    def agent(snapshot, mem, long, errors):
        if state["fail"]:
            raise RuntimeError("llm down")
        return grounded_update()

    runner, _reg, _ = build(tmp_path, agent=agent)
    assert runner.run_if_due() == "failed"
    state["fail"] = False
    assert runner.run_if_due() == "done"


def test_fresh_lock_blocks_a_second_run(tmp_path):
    runner, _reg, calls = build(tmp_path)
    (tmp_path / "run.lock").write_text("x")
    assert runner.run_if_due() == "locked"
    assert calls.agent == []


def test_stale_lock_is_cleared(tmp_path):
    runner, _reg, _ = build(tmp_path)
    lock = tmp_path / "run.lock"
    lock.write_text("x")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    assert runner.run_if_due() == "done"
    assert not lock.exists()


def test_status_defaults_to_idle_when_missing_or_corrupt(tmp_path):
    assert read_status(tmp_path)["stage"] == "idle"
    (tmp_path / "status.json").write_text("{not json")
    assert read_status(tmp_path)["stage"] == "idle"
