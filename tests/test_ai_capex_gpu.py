import json
from datetime import date
from pathlib import Path

import pytest

from castelino.dashboards.ai_capex import gpu

FIXTURE = (Path(__file__).parent / "fixtures" / "ai_capex" / "silicon_index.html").read_text()


def test_parse_fixture():
    rows = {r["gpu"]: r for r in gpu.parse(FIXTURE)}
    assert set(rows) == set(gpu.GPUS)
    assert rows["H100"] == {"gpu": "H100", "price": 2.90, "change_7d_pct": 6.2}
    assert rows["A100"] == {"gpu": "A100", "price": 1.56, "change_7d_pct": -0.6}  # arrow down
    assert rows["B200"]["price"] == 6.47


def test_parse_changed_page_raises():
    with pytest.raises(ValueError):
        gpu.parse("<html><body><p>We redesigned the page</p></body></html>")


def test_same_day_reading_replaces(tmp_path):
    path = tmp_path / "gpu_prices.jsonl"
    gpu.record([{"gpu": "H100", "price": 2.8, "change_7d_pct": 1.0}], "2026-10-27", path)
    gpu.record([{"gpu": "H100", "price": 2.9, "change_7d_pct": 6.2}], "2026-10-28", path)
    hist = gpu.record([{"gpu": "H100", "price": 2.95, "change_7d_pct": 7.0}], "2026-10-28", path)
    assert [(h["date"], h["price"]) for h in hist] == [("2026-10-27", 2.8), ("2026-10-28", 2.95)]
    assert len(path.read_text().splitlines()) == 2


def test_lane(tmp_path):
    out = gpu.lane(tmp_path / "g.jsonl", get_text=lambda url: FIXTURE, today=date(2026, 10, 28))
    assert out["as_of"] == "2026-10-28" and len(out["rows"]) == 6
    assert out["history"][0] == {
        "date": "2026-10-28",
        "gpu": out["rows"][0]["gpu"],
        "price": out["rows"][0]["price"],
    }
    assert out["source"]["url"] == gpu.URL
    assert json.loads((tmp_path / "g.jsonl").read_text().splitlines()[0])["date"] == "2026-10-28"
