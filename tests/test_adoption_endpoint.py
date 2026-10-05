import pytest
from fastapi.testclient import TestClient

from castelino.adoption.index import aggregate
from castelino.adoption.models import Claim, Company, CompanyScore
from castelino.adoption.store import AdoptionStore
from castelino.dashboard.endpoints import adoption as ep


@pytest.fixture
def client(tmp_path, monkeypatch):
    from castelino.dashboard.main import app

    monkeypatch.setattr(ep, "_store_path", tmp_path / "a.db", raising=False)
    return TestClient(app)


def seed(path):
    store = AdoptionStore(path)
    scores = [
        CompanyScore(
            Company("A", "large", "Energy", 10.0),
            {"talk": 1.0},
            {"talk": 60.0, "hire": 55.0, "spend": 65.0},
            60.0,
            3,
            accession="acc-A",
        ),
        CompanyScore(
            Company("B", "large", "Energy", 5.0),
            {},
            {"talk": 40.0, "hire": None, "spend": 50.0},
            45.0,
            2,
        ),
        CompanyScore(
            Company("C", "small", "Energy", 2.0),
            {},
            {"talk": 30.0, "hire": 30.0, "spend": 30.0},
            30.0,
            3,
        ),
    ]
    store.put_filing("A", "acc-A", 1000, 1.0, [Claim(quote="we deployed AI", depth=2)])
    store.save_period("2026-10-01", scores, aggregate(scores))


def test_summary_empty_store_is_an_empty_state_not_an_error(client):
    r = client.get("/adoption/summary")
    assert r.status_code == 200
    assert r.json() == {"period": None, "headline": {}, "series": [], "cells": []}


def test_summary_with_data(client, tmp_path):
    seed(tmp_path / "a.db")
    body = client.get("/adoption/summary").json()
    assert body["period"] == "2026-10-01"
    assert body["headline"]["large_ew"] == pytest.approx(52.5)
    assert body["headline"]["spread"] == pytest.approx(-22.5)
    assert body["series"] == [{"period": "2026-10-01", "large_ew": 52.5, "small_ew": 30.0}]
    assert {(c["sector"], c["bucket"], c["n"], c["thin"]) for c in body["cells"]} == {
        ("Energy", "large", 2, True),
        ("Energy", "small", 1, True),
    }


def test_companies_drilldown(client, tmp_path):
    seed(tmp_path / "a.db")
    rows = client.get("/adoption/companies", params={"sector": "Energy", "bucket": "large"}).json()
    assert [r["ticker"] for r in rows] == ["A", "B"]
    assert rows[0]["score"] == 60.0 and rows[0]["claims"] == [
        {"depth": 2, "quote": "we deployed AI"}
    ]
    assert rows[1]["claims"] == []


def test_companies_rejects_bad_bucket_and_handles_empty_store(client):
    assert (
        client.get("/adoption/companies", params={"sector": "Energy", "bucket": "mid"}).status_code
        == 400
    )
    assert (
        client.get("/adoption/companies", params={"sector": "Energy", "bucket": "large"}).json()
        == []
    )


def test_summary_carries_period_stats(client, tmp_path):
    seed(tmp_path / "a.db")
    stats = client.get("/adoption/summary").json()["stats"]
    assert stats["n_companies"] == 3 and stats["n_scored"] == 3 and stats["n_claims"] == 1
    assert set(stats["pillar_coverage"]) == {"talk", "hire", "spend"}


def test_companies_without_filters_lists_every_company(client, tmp_path):
    seed(tmp_path / "a.db")
    rows = client.get("/adoption/companies").json()
    assert [r["ticker"] for r in rows] == ["A", "B", "C"]
