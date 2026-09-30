import threading

import pytest
from fastapi.testclient import TestClient

from castelino.agents.update.models import DailyRecord
from castelino.agents.update.registry import ModelRegistry
from tests.update_fixtures import make_forecast, make_snapshot, make_update


@pytest.fixture
def client(tmp_path, monkeypatch):
    from castelino.dashboard.endpoints import macro, update

    monkeypatch.setattr(update, "_dirs", lambda: (tmp_path, tmp_path / "updates"))
    monkeypatch.setattr(macro, "_update_root", lambda: tmp_path)
    from castelino.dashboard.main import app

    return TestClient(app), tmp_path


def write_briefing(tmp_path, day):
    d = tmp_path / "updates"
    d.mkdir(exist_ok=True)
    rec = DailyRecord(
        date=day, generated_at=f"{day}T07:30:00", snapshot=make_snapshot(), update=make_update()
    )
    (d / f"{day}.json").write_text(rec.model_dump_json())


def test_status_idle_by_default(client):
    c, _ = client
    body = c.get("/update/status").json()
    assert body["stage"] == "idle" and body["has_today"] is False


def test_latest_404_then_returns_newest(client):
    c, tmp = client
    assert c.get("/update/latest").status_code == 404
    write_briefing(tmp, "2026-09-29")
    write_briefing(tmp, "2026-09-30")
    assert c.get("/update/latest").json()["date"] == "2026-09-30"


def test_history_newest_first_and_by_date(client):
    c, tmp = client
    write_briefing(tmp, "2026-09-29")
    write_briefing(tmp, "2026-09-30")
    assert c.get("/update/history").json()["dates"] == ["2026-09-30", "2026-09-29"]
    assert c.get("/update/2026-09-29").json()["date"] == "2026-09-29"
    assert c.get("/update/2026-01-01").status_code == 404
    assert c.get("/update/not-a-date").status_code == 404


def test_regime_forecast_reads_registry_and_never_retrains(client, monkeypatch):
    c, tmp = client
    reg = ModelRegistry(tmp / "models")
    v = reg.save_version(make_forecast(g_prob=0.71, i_prob=0.87))
    reg.set_pointer("growth", v)
    reg.set_pointer("inflation", v)
    body = c.get("/regime_forecast").json()
    assert body["growth_prob"] == 0.71 and body["inflation_up"] is True and body["running"] is False
    (tmp / "status.json").write_text('{"stage": "refitting"}')
    assert c.get("/regime_forecast").json()["running"] is True


def test_startup_hook_runs_runner_in_background(monkeypatch):
    done = threading.Event()

    class FakeRunner:
        def run_if_due(self):
            done.set()
            return "done"

    monkeypatch.setattr("castelino.agents.update.runner.build_default_runner", lambda: FakeRunner())
    from castelino.dashboard.main import _start_update_agent

    _start_update_agent()
    assert done.wait(2)


def test_startup_hook_respects_disabled_flag(monkeypatch):
    called = []

    class Cfg:
        class update_agent:  # noqa: N801
            enabled = False

    monkeypatch.setattr("castelino.config.get_settings", lambda: Cfg)
    monkeypatch.setattr(
        "castelino.agents.update.runner.build_default_runner", lambda: called.append(1)
    )
    from castelino.dashboard.main import _start_update_agent

    _start_update_agent()
    assert called == []
