from fastapi.testclient import TestClient


def test_ckm_serve_routes_trade_lab_before_the_daily_desk(monkeypatch, tmp_path):
    """/admin/desk/{day} must not swallow /admin/desk/trade (it answered "day must be YYYY-MM-DD")."""
    monkeypatch.setenv("ARC_TRADE_DIR", str(tmp_path / "trades"))
    from castelino.dashboard.main import app

    assert TestClient(app).get("/admin/desk/trade").json() == {"ideas": []}
