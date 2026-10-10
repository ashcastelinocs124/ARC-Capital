import importlib.util
import json
import zlib
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from castelino.cross_asset import run as r

NY = ZoneInfo("America/New_York")


def _series(end="2026-10-09", key="x"):
    idx = pd.date_range("2018-01-01", end, freq="B")
    rng = np.random.default_rng(zlib.crc32(key.encode()))  # stable across processes
    return pd.Series(100 + rng.normal(size=len(idx)).cumsum() * 0.1, index=idx)


def _run(tmp_path, now, **kw):
    kw.setdefault("fetch_fred", lambda sid: _series(key=sid))
    kw.setdefault("fetch_yf", lambda sym: _series(key=sym))
    kw.setdefault("fetch_cftc", lambda code: _series(key=code).resample("W-TUE").last())
    kw.setdefault("search", lambda s, u: ("", []))
    return r.run(now, out=tmp_path / "cross_asset.json", cache=tmp_path / "c.json", **kw)


@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 10, 9, 15, 0, tzinfo=NY), date(2026, 10, 2)),  # Friday before the close
        (datetime(2026, 10, 9, 17, 0, tzinfo=NY), date(2026, 10, 9)),  # Friday after the close
        (datetime(2026, 10, 11, 9, 0, tzinfo=NY), date(2026, 10, 9)),  # Sunday
        (datetime(2026, 10, 14, 9, 0, tzinfo=NY), date(2026, 10, 9)),  # Wednesday
    ],
)
def test_last_completed_friday(now, expected):
    assert r.last_completed_friday(now) == expected


def test_run_writes_snapshot_then_skips_same_week(tmp_path):
    now = datetime(2026, 10, 10, 9, 0, tzinfo=NY)
    msg = _run(tmp_path, now)
    data = json.loads((tmp_path / "cross_asset.json").read_text())
    assert data["week_end"] == "2026-10-09"
    assert set(data["assets"]) == {"spx", "ief", "gld"}
    assert data["assets"]["spx"]["summary"].startswith("Biggest drivers:")
    assert "explained" in msg
    with pytest.raises(r.NothingToDo):
        _run(tmp_path, now)


def test_partial_week_is_recomputed_on_the_next_run(tmp_path):
    now = datetime(2026, 10, 9, 17, 0, tzinfo=NY)  # the scheduled Friday run
    # FRED hasn't posted Friday yet: daily FRED series end Thursday
    _run(tmp_path, now, fetch_fred=lambda sid: _series(end="2026-10-08", key=sid))
    first = json.loads((tmp_path / "cross_asset.json").read_text())
    assert first["week_end"] == "2026-10-09" and first["partial"] is True
    _run(tmp_path, datetime(2026, 10, 12, 17, 0, tzinfo=NY))  # Monday: Friday is in
    second = json.loads((tmp_path / "cross_asset.json").read_text())
    assert second["week_end"] == "2026-10-09" and second["partial"] is False
    with pytest.raises(r.NothingToDo):  # complete now: locked for the week
        _run(tmp_path, datetime(2026, 10, 13, 17, 0, tzinfo=NY))


def test_stale_asset_keeps_previous_file(tmp_path):
    prev = {"week_end": "2026-10-02", "assets": {}}
    (tmp_path / "cross_asset.json").write_text(json.dumps(prev))
    with pytest.raises(Exception, match="Gold"):
        _run(
            tmp_path,
            datetime(2026, 10, 10, 9, 0, tzinfo=NY),
            fetch_yf=lambda sym: (
                _series(end="2026-10-01", key=sym) if sym == "GLD" else _series(key=sym)
            ),
        )
    assert json.loads((tmp_path / "cross_asset.json").read_text()) == prev


def test_endpoint_serves_file_or_empty(tmp_path, monkeypatch):
    from castelino.dashboard.main import app

    monkeypatch.setattr(r, "out_path", lambda: tmp_path / "cross_asset.json")
    client = TestClient(app)
    assert client.get("/cross_asset").json() == {}
    (tmp_path / "cross_asset.json").write_text(json.dumps({"week_end": "2026-10-09", "assets": {}}))
    assert client.get("/cross_asset").json()["week_end"] == "2026-10-09"


def test_export_and_refresh_wiring():
    from castelino.dashboard.endpoints import refresh

    spec = importlib.util.spec_from_file_location(
        "export_snapshot", Path(__file__).resolve().parents[1] / "scripts" / "export_snapshot.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "/cross_asset" in mod.PATHS
    assert "cross_asset" in refresh._RUNNERS
    assert refresh.LABELS["cross_asset"] == "Cross-Asset Drivers"
