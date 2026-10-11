import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

from castelino.dashboard.endpoints import weekly as ep
from castelino.dashboard.main import app


def write(d, week, title):
    d.mkdir(parents=True, exist_ok=True)
    rec = {"version": 1, "week": week, "start": "s", "end": "e", "report": {"title": title}}
    (d / f"{week}.json").write_text(json.dumps(rec))


def test_history_latest_and_by_week(tmp_path, monkeypatch):
    monkeypatch.setattr(ep, "_dir", lambda: tmp_path)
    write(tmp_path, "2026-W40", "Old")
    write(tmp_path, "2026-W41", "New")
    c = TestClient(app)
    items = c.get("/weekly/history").json()["items"]
    assert [i["week"] for i in items] == ["2026-W41", "2026-W40"] and items[0]["title"] == "New"
    assert c.get("/weekly/latest").json()["week"] == "2026-W41"
    assert c.get("/weekly/2026-W40").json()["report"]["title"] == "Old"
    assert c.get("/weekly/2026-W99").status_code == 404
    assert c.get("/weekly/not-a-week").status_code == 404


def test_latest_404_when_empty_and_status_reports_due(tmp_path, monkeypatch):
    monkeypatch.setattr(ep, "_dir", lambda: tmp_path)
    c = TestClient(app)
    assert c.get("/weekly/latest").status_code == 404
    st = c.get("/weekly/status").json()
    assert st["stage"] == "idle" and "due" in st


def test_chart_route_only_serves_exhibit_pngs(tmp_path, monkeypatch):
    monkeypatch.setattr(ep, "_dir", lambda: tmp_path)
    p = tmp_path / "charts" / "2026-W41"
    p.mkdir(parents=True)
    (p / "exhibit_1.png").write_bytes(b"\x89PNG")
    (p / "secret.txt").write_text("x")
    c = TestClient(app)
    assert c.get("/weekly/2026-W41/charts/exhibit_1.png").status_code == 200
    assert c.get("/weekly/2026-W41/charts/secret.txt").status_code == 404


def test_export_copies_weekly_charts(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "export_snapshot", Path(__file__).resolve().parents[1] / "scripts" / "export_snapshot.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "OUT", tmp_path / "out")
    src = tmp_path / "deep" / "charts" / "2026-W41"
    src.mkdir(parents=True)
    (src / "exhibit_1.png").write_bytes(b"x")
    rec = {"exhibits": [{"file": "exhibit_1.png"}, {"file": "exhibit_2.png"}]}
    assert mod.copy_weekly_charts("2026-W41", rec, tmp_path / "deep") == 1
    assert (tmp_path / "out" / "weekly" / "2026-W41" / "charts" / "exhibit_1.png").exists()
    assert "/weekly/history" in mod.PATHS and "/weekly/latest" in mod.PATHS
