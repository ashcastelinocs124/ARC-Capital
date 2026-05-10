"""Phase-4 tests: rolling classifier retrain — no-lookahead invariant +
artifact persistence + nearest-neighbor lookup."""
from __future__ import annotations

import pickle
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from castelino.backtest import rolling_train as rt


def _make_series(start: str, end: str, freq: str = "MS") -> pd.Series:
    """Synthetic monthly indicator: 1.0 + 0.1 * month index."""
    idx = pd.date_range(start, end, freq=freq)
    vals = [1.0 + 0.1 * i for i in range(len(idx))]
    return pd.Series(vals, index=idx, name="x")


def test_make_as_of_provider_truncates_strictly_before(tmp_path):
    """Every returned series must have all timestamps strictly < as_of."""
    base_series = _make_series("2020-01-01", "2024-12-01")

    def base_provider(specs):
        return {spec.id: base_series.copy() for spec in specs}

    class _Spec:
        id = "x"

    cutoff = date(2024, 3, 15)
    wrapped = rt.make_as_of_provider(cutoff, base_provider)
    out = wrapped([_Spec()])

    assert "x" in out
    assert all(ts < pd.Timestamp(cutoff) for ts in out["x"].index)
    # Nothing on or after the cutoff
    assert pd.Timestamp(cutoff) not in out["x"].index


def test_make_as_of_provider_no_lookahead_at_day_100():
    """Concrete check: trained on day-100, only day-1..99 are visible."""
    series = pd.Series(
        range(100), index=pd.date_range("2024-01-01", periods=100, freq="D"),
    )
    def base(specs):
        return {s.id: series for s in specs}

    class _S: id = "y"
    wrapped = rt.make_as_of_provider(date(2024, 4, 9), base)  # day-100
    truncated = wrapped([_S()])["y"]
    # Day 100 is 2024-04-09; cutoff is strict <, so we expect days 1..99
    assert len(truncated) == 99
    assert truncated.index.max() == pd.Timestamp("2024-04-08")


def test_make_as_of_provider_handles_tz_aware_index():
    series = pd.Series(
        range(10),
        index=pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC"),
    )
    def base(specs): return {s.id: series for s in specs}
    class _S: id = "tz"
    wrapped = rt.make_as_of_provider(date(2024, 1, 5), base)
    out = wrapped([_S()])["tz"]
    # Strict < cutoff: rows from 1/1 through 1/4 → 4 rows
    assert len(out) == 4


def test_load_nearest_returns_none_when_no_artifacts(monkeypatch, tmp_path):
    cfg = rt.get_settings()
    monkeypatch.setattr(cfg.backtest, "runs_dir", str(tmp_path / "runs"))
    assert rt.load_nearest("nonexistent-run", date(2024, 3, 15)) is None


def test_load_nearest_finds_most_recent_on_or_before(monkeypatch, tmp_path):
    cfg = rt.get_settings()
    monkeypatch.setattr(cfg.backtest, "runs_dir", str(tmp_path / "runs"))
    base = tmp_path / "runs" / "test-run" / "models"
    for d in ["2024-03-03", "2024-03-10", "2024-03-17", "2024-03-24"]:
        (base / d).mkdir(parents=True)
        (base / d / "growth.pkl").write_bytes(b"stub-growth")
        (base / d / "inflation.pkl").write_bytes(b"stub-infl")

    nearest = rt.load_nearest("test-run", date(2024, 3, 15))
    assert nearest is not None
    assert nearest.as_of == date(2024, 3, 10)  # most recent ≤ 3/15

    # Exact-match still picks that day
    exact = rt.load_nearest("test-run", date(2024, 3, 17))
    assert exact is not None and exact.as_of == date(2024, 3, 17)

    # Before the earliest artifact — None
    assert rt.load_nearest("test-run", date(2024, 2, 1)) is None


def test_retrain_classifiers_writes_artifacts(monkeypatch, tmp_path):
    """E2E: an injected provider feeds toy data, retrain writes pickles."""
    cfg = rt.get_settings()
    monkeypatch.setattr(cfg.backtest, "runs_dir", str(tmp_path / "runs"))

    # Stub training functions — we only care about persistence + the no-lookahead
    # provider plumbing here, not XGBoost's behavior on synthetic series.
    import castelino.backtest.rolling_train as rtmod
    monkeypatch.setattr(
        rtmod, "train_growth_forecast",
        lambda **kw: {"as_of": "growth", "_provider_seen": kw.get("series_provider") is not None},
    )
    monkeypatch.setattr(
        rtmod, "train_inflation_forecast",
        lambda **kw: {"as_of": "inflation", "_provider_seen": kw.get("series_provider") is not None},
    )

    artifact = rt.retrain_classifiers(as_of=date(2024, 3, 17), run_id="test-train")
    assert artifact.as_of == date(2024, 3, 17)
    assert artifact.growth_path.exists()
    assert artifact.inflation_path.exists()

    g = pickle.loads(artifact.growth_path.read_bytes())
    i = pickle.loads(artifact.inflation_path.read_bytes())
    assert g["as_of"] == "growth" and g["_provider_seen"]
    assert i["as_of"] == "inflation" and i["_provider_seen"]


def test_retrain_4_weeks_smoke_each_writes_distinct_dir(monkeypatch, tmp_path):
    """The plan's 4-week smoke test: 4 retrains across a month, each
    producing its own dated artifact directory."""
    cfg = rt.get_settings()
    monkeypatch.setattr(cfg.backtest, "runs_dir", str(tmp_path / "runs"))

    import castelino.backtest.rolling_train as rtmod
    monkeypatch.setattr(rtmod, "train_growth_forecast", lambda **kw: {"k": "g"})
    monkeypatch.setattr(rtmod, "train_inflation_forecast", lambda **kw: {"k": "i"})

    sundays = [date(2024, 3, 3), date(2024, 3, 10),
               date(2024, 3, 17), date(2024, 3, 24)]
    for s in sundays:
        rt.retrain_classifiers(as_of=s, run_id="bt-4w")

    base = tmp_path / "runs" / "bt-4w" / "models"
    assert sorted(p.name for p in base.iterdir()) == [d.isoformat() for d in sundays]

    # Picking any mid-week date returns the prior Sunday's artifact
    art = rt.load_nearest("bt-4w", date(2024, 3, 14))  # Thu
    assert art.as_of == date(2024, 3, 10)
