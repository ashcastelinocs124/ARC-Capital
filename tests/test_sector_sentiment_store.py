"""Universe cache, snapshot persistence, history z-score."""

import json
from datetime import UTC, datetime

import pytest

from castelino.signals import sector_sentiment as ss
from castelino.signals.sector_sentiment import (
    SectorScore,
    SectorSentimentSnapshot,
    StockRow,
)


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_store_path", lambda: tmp_path / "sector_sentiment.json")
    monkeypatch.setattr(ss, "_universe_path", lambda: tmp_path / "sector_universe.json")
    return tmp_path


def _snap(div=0.5) -> SectorSentimentSnapshot:
    return SectorSentimentSnapshot(
        as_of=datetime(2026, 8, 29, 15, 0, tzinfo=UTC),
        sectors=[
            SectorScore(
                sector="Technology",
                etf="XLK",
                divergence=div,
                tech_score=0.6,
                fund_score=0.1,
                label="euphoric",
            )
        ],
        stocks=[
            StockRow(
                symbol="NVDA",
                name="NVIDIA",
                sector="Technology",
                market_cap=3.4e12,
                rsi14=78,
                macd_hist=1.2,
                vs_sma50=0.1,
                vs_sma200=0.31,
                ret_3m=0.24,
                rev_yoy=0.62,
                earnings_growth=0.02,
                pe_rel=2.1,
                tech_score=0.92,
                fund_score=0.11,
                divergence=0.81,
            )
        ],
    )


def test_load_snapshot_empty(tmp_store):
    assert ss.load_snapshot() is None


def test_save_and_load_roundtrip(tmp_store):
    ss.save_snapshot(_snap())
    loaded = ss.load_snapshot()
    assert loaded is not None
    assert loaded.sectors[0].etf == "XLK"
    assert loaded.stocks[0].symbol == "NVDA"


def test_history_appends_once_per_day(tmp_store):
    ss.save_snapshot(_snap(0.5))
    ss.save_snapshot(_snap(0.6))  # same as_of date -> replace, not append
    raw = json.loads(ss._store_path().read_text())
    tech_rows = [h for h in raw["history"] if h["sector"] == "Technology"]
    assert len(tech_rows) == 1
    assert tech_rows[0]["divergence"] == 0.6


def test_history_zscore_needs_min_obs():
    hist = [
        {"date": f"2026-08-{d:02d}", "sector": "Technology", "divergence": 0.1}
        for d in range(1, 10)
    ]
    assert ss.history_zscore("Technology", 0.5, hist, min_obs=20) is None
    hist = [
        {"date": f"2026-07-{d:02d}", "sector": "Technology", "divergence": 0.1 + (d % 5) * 0.05}
        for d in range(1, 26)
    ]
    z = ss.history_zscore("Technology", 0.9, hist, min_obs=20)
    assert z is not None and z > 1.0


def test_get_universe_uses_cache(tmp_store, monkeypatch):
    calls = []

    def fake_top(sector_key, limit):
        calls.append(sector_key)
        return [
            {"symbol": "AAA", "name": "A Corp"},
            {"symbol": "BBB", "name": "B Corp"},
        ]

    def fake_industries(keys, limit):
        calls.append(keys)
        return [{"symbol": "NVDA", "name": "NVIDIA", "market_cap": 5e12}]

    monkeypatch.setattr(ss, "_yf_top_companies", fake_top)
    monkeypatch.setattr(ss, "_yf_top_industries", fake_industries)
    uni = ss.get_universe()
    assert len(calls) == 12  # one screen per sector + the Semiconductors overlay
    assert uni["Technology"][0]["symbol"] == "AAA"
    assert uni["Semiconductors"][0]["symbol"] == "NVDA"
    calls.clear()
    uni2 = ss.get_universe()  # second call inside TTL -> cache, no API
    assert calls == []
    assert uni2 == uni

    # a cache written before the overlay existed is refetched, not served without it
    raw = json.loads(ss._universe_path().read_text())
    del raw["universe"]["Semiconductors"]
    ss._universe_path().write_text(json.dumps(raw))
    assert "Semiconductors" in ss.get_universe()
    assert len(calls) == 12
