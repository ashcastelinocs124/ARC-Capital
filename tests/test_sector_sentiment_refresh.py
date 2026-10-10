"""refresh(): end-to-end with faked universe/collection; throttle + averages."""

import pytest

from castelino.signals import sector_sentiment as ss


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_store_path", lambda: tmp_path / "sector_sentiment.json")
    monkeypatch.setattr(ss, "_universe_path", lambda: tmp_path / "sector_universe.json")


@pytest.fixture(autouse=True)
def fake_universe(monkeypatch):
    monkeypatch.setattr(
        ss,
        "get_universe",
        lambda force=False: {
            "Technology": [
                {"symbol": "NVDA", "name": "NVIDIA", "market_cap": 3.4e12},
                {"symbol": "ADBE", "name": "Adobe", "market_cap": 2.1e11},
            ],
            "Energy": [
                {"symbol": "XOM", "name": "Exxon", "market_cap": 4.7e11},
            ],
        },
    )


@pytest.fixture(autouse=True)
def fake_rows(monkeypatch):
    def _collect(universe):
        rows = []
        spec = {
            "NVDA": dict(rsi14=78.0, ret_3m=0.24, rev_yoy=0.62, pe_rel=2.1),
            "ADBE": dict(rsi14=42.0, ret_3m=-0.04, rev_yoy=0.10, pe_rel=0.9),
            "XOM": dict(rsi14=34.0, ret_3m=-0.08, rev_yoy=0.07, pe_rel=0.8),
        }
        for sector, members in universe.items():
            for m in members:
                s = spec[m["symbol"]]
                rows.append(
                    ss.StockRow(
                        symbol=m["symbol"],
                        name=m["name"],
                        sector=sector,
                        market_cap=m["market_cap"],
                        rsi14=s["rsi14"],
                        macd_hist=0.0,
                        vs_sma50=0.0,
                        vs_sma200=0.0,
                        ret_3m=s["ret_3m"],
                        rev_yoy=s["rev_yoy"],
                        earnings_growth=0.0,
                        pe_rel=s["pe_rel"],
                    )
                )
        return rows

    monkeypatch.setattr(ss, "collect_rows", _collect)


def test_refresh_persists_snapshot():
    snap = ss.refresh()
    assert snap.narrative is None  # narrative is added later by the Claude explainer
    assert {s.sector for s in snap.sectors} == {"Technology", "Energy"}
    assert ss.load_snapshot() is not None


def test_refresh_throttles_within_interval(monkeypatch):
    """A snapshot younger than refresh_interval_hours short-circuits refresh."""
    calls = []
    real_collect = ss.collect_rows
    monkeypatch.setattr(ss, "collect_rows", lambda u: (calls.append(1), real_collect(u))[1])

    first = ss.refresh()
    assert len(calls) == 1
    second = ss.refresh()  # within 24h -> stored snapshot, no new work
    assert len(calls) == 1
    assert second.as_of == first.as_of
    third = ss.refresh(force=True)  # force bypasses the throttle
    assert len(calls) == 2
    assert third.as_of >= first.as_of


@pytest.mark.parametrize("lost", [{"XOM"}, {"NVDA", "ADBE", "XOM"}])
def test_refresh_missing_a_sector_keeps_previous_snapshot(monkeypatch, lost):
    """A Yahoo outage (no fundamentals, cap 0) for some or all stocks must not overwrite a good
    snapshot with fewer sectors (on 2026-10-09 it saved 0 of 11, then 4 of 11)."""
    good = ss.refresh()
    real_collect = ss.collect_rows

    def outage(u):
        gone = dict(rev_yoy=None, earnings_growth=None, pe_rel=None, market_cap=0.0)
        return [r.model_copy(update=gone) if r.symbol in lost else r for r in real_collect(u)]

    monkeypatch.setattr(ss, "collect_rows", outage)
    with pytest.raises(RuntimeError, match="Energy"):
        ss.refresh(force=True)
    assert ss.load_snapshot().as_of == good.as_of


def test_aggregate_averages_are_cap_weighted():
    rows = ss.score_stocks(ss.collect_rows(ss.get_universe()))
    sectors = {s.sector: s for s in ss.aggregate_sectors(rows)}
    tech = sectors["Technology"]
    members = [r for r in rows if r.sector == "Technology" and r.divergence is not None]
    cap = sum(r.market_cap for r in members)
    expected = sum(r.divergence * r.market_cap for r in members) / cap
    assert tech.avg_divergence == pytest.approx(expected)
    assert tech.avg_tech is not None and tech.avg_fund is not None
    # avg_* mirror the headline cap-weighted fields (equal-weight retired)
    assert tech.avg_divergence == pytest.approx(tech.divergence)
