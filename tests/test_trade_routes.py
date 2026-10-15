from fastapi.testclient import TestClient


def test_ckm_serve_routes_trade_lab_before_the_daily_desk(monkeypatch, tmp_path):
    """/admin/desk/{day} must not swallow /admin/desk/trade (it answered "day must be YYYY-MM-DD")."""
    monkeypatch.setenv("ARC_TRADE_DIR", str(tmp_path / "trades"))
    from castelino.dashboard.main import app

    assert TestClient(app).get("/admin/desk/trade").json() == {"ideas": []}


def test_ckm_serve_marks_steps_a_restart_killed(monkeypatch, tmp_path):
    monkeypatch.setenv("ARC_TRADE_DIR", str(tmp_path / "trades"))
    from castelino.agents.trade import store
    from castelino.agents.trade.models import Job
    from castelino.dashboard.main import app
    from castelino.data import openbb_adapter

    monkeypatch.setattr(openbb_adapter, "get_adapter", lambda: None)  # skip the OpenBB warm-up
    i = store.create("India")
    i.job = Job(step="research", state="running", at="t")
    store.save(i)
    with TestClient(app):  # runs the startup hooks
        pass
    assert store.load(i.id).job.state == "interrupted"
