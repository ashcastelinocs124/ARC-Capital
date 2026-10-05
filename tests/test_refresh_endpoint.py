import pytest
from fastapi.testclient import TestClient

from castelino.dashboard.endpoints import refresh as ep


@pytest.fixture
def client(monkeypatch):
    from castelino.dashboard.main import app

    monkeypatch.setattr(ep, "_state", {}, raising=False)
    return TestClient(app)


def _jobs(monkeypatch, **fns):
    monkeypatch.setattr(ep, "_RUNNERS", fns)


def test_status_idle_before_any_refresh(client, monkeypatch):
    _jobs(monkeypatch, a=lambda: "ok")
    body = client.get("/refresh/status").json()
    assert body["running"] is False
    assert [j["status"] for j in body["jobs"]] == ["idle"]


def test_refresh_runs_every_job_and_records_outcomes(client, monkeypatch):
    def boom():
        raise RuntimeError("no key")

    def skip():
        raise ep.Skipped("already done today")

    _jobs(monkeypatch, ok=lambda: "wrote 3 rows", bad=boom, skip=skip)
    r = client.post("/refresh")
    assert r.status_code == 202
    ep._wait(5)
    jobs = {j["key"]: j for j in client.get("/refresh/status").json()["jobs"]}
    assert jobs["ok"]["status"] == "done" and jobs["ok"]["message"] == "wrote 3 rows"
    assert jobs["bad"]["status"] == "failed" and "no key" in jobs["bad"]["message"]
    assert jobs["skip"]["status"] == "skipped" and jobs["skip"]["message"] == "already done today"
    assert all(j["finished_at"] for j in jobs.values())


def test_second_refresh_while_running_is_rejected(client, monkeypatch):
    import threading

    gate = threading.Event()
    _jobs(monkeypatch, slow=lambda: gate.wait(5) and "done")
    assert client.post("/refresh").status_code == 202
    assert client.get("/refresh/status").json()["running"] is True
    assert client.post("/refresh").status_code == 409
    gate.set()
    ep._wait(5)
    assert client.get("/refresh/status").json()["running"] is False


def test_server_start_no_longer_runs_refreshes():
    from castelino.dashboard.main import app

    names = {h.__name__ for h in app.router.on_startup}
    assert "_start_update_agent" not in names and "_start_sector_sentiment" not in names


def test_update_agent_job_runs_runner_and_reports(monkeypatch):
    class FakeRunner:
        def run_if_due(self):
            return "done"

    monkeypatch.setattr("castelino.agents.update.runner.build_default_runner", lambda: FakeRunner())
    assert "briefing" in ep.job_update_agent().lower()


def test_update_agent_job_skips_when_already_done_or_disabled(monkeypatch):
    class FakeRunner:
        def run_if_due(self):
            return "skipped"

    monkeypatch.setattr("castelino.agents.update.runner.build_default_runner", lambda: FakeRunner())
    with pytest.raises(ep.Skipped):
        ep.job_update_agent()

    class Cfg:
        class update_agent:  # noqa: N801
            enabled = False

    monkeypatch.setattr("castelino.config.get_settings", lambda: Cfg)
    with pytest.raises(ep.Skipped, match="disabled"):
        ep.job_update_agent()
