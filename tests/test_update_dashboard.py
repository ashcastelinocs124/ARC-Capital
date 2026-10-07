import json

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
    hist = c.get("/update/history").json()
    assert hist["dates"] == ["2026-09-30", "2026-09-29"]
    headline = make_update().headline
    assert hist["items"] == [
        {"date": "2026-09-30", "headline": headline},
        {"date": "2026-09-29", "headline": headline},
    ]
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


# Startup refresh moved to the dashboard Refresh button: see tests/test_refresh_endpoint.py


def test_history_survives_a_malformed_briefing(client):
    c, tmp = client
    write_briefing(tmp, "2026-09-29")
    (tmp / "updates" / "2026-09-30.json").write_text("{not json")
    items = c.get("/update/history").json()["items"]
    assert items[0] == {"date": "2026-09-30", "headline": ""}
    assert items[1]["headline"]


def _v2(day, headline="Morning headline"):
    return {
        "version": 2,
        "date": day,
        "generated_at": f"{day}T07:00:00",
        "findings": [],
        "note": {
            "headline": headline,
            "takeaways": ["a", "b", "c"],
            "items": [],
            "themes_touched": [],
            "new_themes": [],
        },
        "exhibits": [
            {
                "n": 1,
                "finding_id": "macro-1",
                "title": "t",
                "subtitle": "s",
                "file": "exhibit_1.png",
            }
        ],
        "releases": [],
        "rounds": 0,
        "data_gaps": [],
    }


def test_history_reads_v2_headline(client):
    c, tmp = client
    (tmp / "updates").mkdir()
    (tmp / "updates" / "2026-10-07.json").write_text(json.dumps(_v2("2026-10-07")))
    items = c.get("/update/history").json()["items"]
    assert items[0] == {"date": "2026-10-07", "headline": "Morning headline"}


def test_chart_png_served_and_bad_names_404(client):
    c, tmp = client
    d = tmp / "updates" / "charts" / "2026-10-07"
    d.mkdir(parents=True)
    (d / "exhibit_1.png").write_bytes(b"\x89PNG fake")
    r = c.get("/update/2026-10-07/charts/exhibit_1.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert c.get("/update/2026-10-07/charts/exhibit_2.png").status_code == 404
    # ".." is normalised before routing; it must never reach the chart route as a file name
    r = c.get("/update/2026-10-07/charts/..%2Fsecret.png")
    assert r.headers.get("content-type") != "image/png"
    assert c.get("/update/bad-day/charts/exhibit_1.png").status_code == 404


def test_export_copies_chart_pngs(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "export_snapshot", Path(__file__).resolve().parents[1] / "scripts" / "export_snapshot.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "OUT", tmp_path / "out")
    d = tmp_path / "updates" / "charts" / "2026-10-07"
    d.mkdir(parents=True)
    (d / "exhibit_1.png").write_bytes(b"png")
    assert mod.copy_charts("2026-10-07", _v2("2026-10-07"), updates_dir=tmp_path / "updates") == 1
    out = tmp_path / "out" / "update" / "2026-10-07" / "charts" / "exhibit_1.png"
    assert out.read_bytes() == b"png"
