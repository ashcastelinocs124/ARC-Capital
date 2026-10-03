"""GET /sector_sentiment + tick() integration is failure-tolerant."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from castelino.signals import sector_sentiment as ss
from castelino.signals.sector_sentiment import (
    SectorScore,
    SectorSentimentSnapshot,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_store_path", lambda: tmp_path / "sector_sentiment.json")
    from castelino.dashboard.main import app

    return TestClient(app)


def _snap():
    return SectorSentimentSnapshot(
        as_of=datetime(2026, 8, 29, 15, 0, tzinfo=UTC),
        sectors=[
            SectorScore(
                sector="Energy",
                etf="XLE",
                divergence=-0.48,
                tech_score=-0.4,
                fund_score=0.08,
                label="fearful",
                zscore=-1.1,
            )
        ],
        stocks=[],
        narrative="Energy is fearful.",
    )


def test_endpoint_empty_state(client):
    r = client.get("/sector_sentiment")
    assert r.status_code == 200
    assert r.json() == {}


def test_endpoint_serves_stored_snapshot(client):
    ss.save_snapshot(_snap())
    r = client.get("/sector_sentiment")
    assert r.status_code == 200
    body = r.json()
    assert body["sectors"][0]["etf"] == "XLE"
    assert body["narrative"] == "Energy is fearful."


def test_endpoint_compute_calls_refresh(client, monkeypatch):
    called = []

    def fake_refresh(force=False):
        called.append(force)
        snap = _snap()
        ss.save_snapshot(snap)
        return snap

    monkeypatch.setattr(ss, "refresh", fake_refresh)
    r = client.get("/sector_sentiment?compute=true")
    assert called == [True]  # endpoint forces past the 24h throttle
    assert r.json()["sectors"][0]["label"] == "fearful"
