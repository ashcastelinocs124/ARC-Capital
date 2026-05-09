import json
import pytest

from tests.backtest.conftest import load_fixtures, FIXTURES_DIR


def test_load_fixtures_returns_empty_for_missing_subdir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tests.backtest.conftest.FIXTURES_DIR", tmp_path,
    )
    assert load_fixtures("nonexistent") == []


def test_load_fixtures_reads_json_files(tmp_path, monkeypatch):
    sub = tmp_path / "demo"
    sub.mkdir()
    (sub / "a.json").write_text(json.dumps({"case_id": "a", "x": 1}))
    (sub / "b.json").write_text(json.dumps({"case_id": "b", "x": 2}))
    (sub / "ignored.txt").write_text("nope")

    monkeypatch.setattr(
        "tests.backtest.conftest.FIXTURES_DIR", tmp_path,
    )
    out = load_fixtures("demo")
    assert {f["case_id"] for f in out} == {"a", "b"}
