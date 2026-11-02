"""Sector Signal Significance: the event detector, the statistics and the whole build on synthetic prices.

The two end-to-end cases are the point: on pure random walks the model must call (almost) nothing a
signal, and when a real edge is planted after one signal on one sector it must find exactly that one."""

import json

import numpy as np
import pandas as pd
import pytest

from castelino.config import SectorSignalsCfg
from castelino.dashboards.sector_signals import run as ss
from castelino.dashboards.sector_signals import signals as sig
from castelino.dashboards.sector_signals import stats as st

IDX = pd.bdate_range("2000-01-03", periods=6000)


def walk(seed: int, n: int = len(IDX), drift: float = 0.0003, vol: float = 0.012) -> pd.DataFrame:
    g = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(g.normal(drift, vol, n)))
    v = g.lognormal(15, 0.4, n)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": v}, index=IDX[:n])


def universe(n: int = len(IDX)) -> tuple[dict[str, pd.DataFrame], pd.Series]:
    prices = {etf: walk(i, n) for i, (_name, etf) in enumerate(ss.SECTORS)}
    prices["SPY"] = walk(99, n)
    g = np.random.default_rng(7)
    vix = pd.Series(np.clip(18 + np.cumsum(g.normal(0, 0.05, n)), 9, 60), index=IDX[:n])
    return prices, vix


CFG = SectorSignalsCfg(bootstrap=1000, bootstrap_regime=300)


# ── signals ────────────────────────────────────────────────────────────────


def test_onsets_count_a_spell_once_and_respect_the_cooldown():
    cond = pd.Series([False, True, True, False, True, False, False, False, True, True])
    assert sig.onsets(cond, cooldown=1).tolist() == [1, 4, 8]
    assert sig.onsets(cond, cooldown=4).tolist() == [1, 8]  # 4 is only 3 days after 1


def test_first_row_is_never_an_onset():
    assert sig.onsets(pd.Series([True, True, False]), cooldown=1).tolist() == []


def test_rsi_is_bounded_and_extreme_on_one_way_moves():
    up = pd.Series(np.linspace(100, 200, 60))
    down = pd.Series(np.linspace(200, 100, 60))
    noise = walk(3, 300)["close"]
    assert sig.rsi(up).iloc[-1] == pytest.approx(100)
    assert sig.rsi(down).iloc[-1] == pytest.approx(0)
    r = sig.rsi(noise).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_golden_cross_fires_once_when_the_trend_turns():
    c = np.r_[np.linspace(200, 100, 300), np.linspace(100, 250, 300)]
    df = pd.DataFrame({"close": c, "volume": 1.0}, index=IDX[:600])
    ev = sig.events(df, df["close"], cooldown=10)
    assert len(ev["golden_cross"]) == 1 and ev["golden_cross"][0] > 300
    assert len(ev["death_cross"]) == 0  # 50-day was already under the 200-day when both existed


def test_warm_up_rows_never_fire():
    df = walk(5, 400)
    ev = sig.events(df, df["close"], cooldown=10)
    assert all(i >= 199 for i in ev["golden_cross"]) and all(i >= 252 for i in ev["high_52w"])


# ── stats ──────────────────────────────────────────────────────────────────


def test_forward_returns_line_up_with_the_close_h_days_later():
    f = st.forward_returns(np.array([100.0, 110.0, 121.0, 133.1]), [1, 2])
    assert f[1][:3] == pytest.approx([0.1, 0.1, 0.1]) and np.isnan(f[1][3])
    assert f[2][0] == pytest.approx(0.21) and np.isnan(f[2][2:]).all()


def test_event_test_finds_a_planted_edge_and_not_a_fake_one():
    g = np.random.default_rng(1)
    fwd = g.normal(0, 0.02, 5000)
    idx = np.sort(g.choice(4900, 60, replace=False))
    offsets = st.shift_offsets(5000, 30, 2000, g)
    assert st.event_test(fwd, idx, 5000, offsets)["p"] > 0.01
    planted = fwd.copy()
    planted[idx] += 0.015
    out = st.event_test(planted, idx, 5000, offsets)
    assert out["p"] < 0.001 and out["edge"] == pytest.approx(0.015, abs=0.006) and out["z"] > 3


def test_p_values_are_roughly_uniform_under_the_null():
    g = np.random.default_rng(2)
    ps = []
    for _ in range(300):
        fwd = g.normal(0, 0.02, 2000)
        idx = np.sort(g.choice(1950, 25, replace=False))
        ps.append(st.event_test(fwd, idx, 2000, st.shift_offsets(2000, 25, 400, g))["p"])
    assert 0.06 < np.mean(np.array(ps) <= 0.1) < 0.14


def test_benjamini_hochberg_matches_the_textbook_example():
    p = [0.01, 0.04, 0.03, 0.005, None]
    q = st.benjamini_hochberg(p)
    assert q[4] is None
    assert q == pytest.approx([0.02, 0.04, 0.04, 0.02, None])


@pytest.mark.parametrize(
    ("n", "p", "q", "want"),
    [
        (5, 0.001, 0.01, "few"),
        (30, 0.001, 0.05, "signal"),
        (30, 0.04, 0.3, "weak"),
        (30, 0.5, 0.9, "noise"),
    ],
)
def test_verdict(n, p, q, want):
    assert st.verdict(n, p, q, min_events=10, fdr=0.1, p_weak=0.1) == want


# ── the whole build ────────────────────────────────────────────────────────


def test_random_walks_produce_no_signals_and_noise_holds_about_half_the_time():
    prices, vix = universe()
    doc = ss.build(prices, vix, CFG)
    called = [t for t in doc["tests"] if t["verdict"] == "signal"]
    assert len(called) <= 3  # BH at 10% on ~500 null tests: expect ~0
    weak_share = np.mean([t["verdict"] == "weak" for t in doc["tests"]])
    assert 0.03 < weak_share < 0.18
    assert 0.38 < doc["summary"]["oos"]["noise"]["rate"] < 0.62


def test_a_planted_edge_is_found_on_its_sector_only():
    prices, vix = universe()
    df = prices["XLE"].copy()
    ret = np.diff(np.log(df["close"].to_numpy()), prepend=np.log(100))
    for _ in range(4):  # planting moves prices, which moves later events: iterate until they settle
        ev = sig.onsets(sig.BY_ID["rsi_oversold"].fn(df, prices["SPY"]["close"]), CFG.cooldown)
        bumped = ret.copy()
        for i in ev:
            bumped[i + 1 : i + 11] += 0.004  # +4% over the next 10 sessions after RSI < 30
        c = 100 * np.exp(np.cumsum(bumped))
        df = df.assign(open=c, high=c, low=c, close=c)
    prices["XLE"] = df
    doc = ss.build(prices, vix, CFG)
    hits = {
        (t["etf"], t["signal"]) for t in doc["tests"] if t["verdict"] == "signal" and t["h"] == 10
    }
    assert ("XLE", "rsi_oversold") in hits
    assert {e for e, _s in hits} == {"XLE"}
    row = next(
        t for t in doc["tests"] if (t["etf"], t["signal"], t["h"]) == ("XLE", "rsi_oversold", 10)
    )
    assert row["edge"] > 0.02 and row["textbook"] is True and row["oos"]["held"] is True
    path = doc["paths"]["XLE|rsi_oversold"]
    assert path["mean"][10] > path["null_hi"][10]


def test_live_events_carry_their_track_record():
    prices, vix = universe()
    doc = ss.build(prices, vix, CFG)
    assert doc["live"], "random walks fire something in the last 5 sessions"
    for e in doc["live"]:
        assert e["sessions_ago"] < CFG.live_lookback_days
        assert e["verdict"] in {"signal", "weak", "noise", "few"} and e["best_h"] in CFG.horizons
    order = {"signal": 0, "weak": 1, "noise": 2, "few": 3}
    assert [order[e["verdict"]] for e in doc["live"]] == sorted(
        order[e["verdict"]] for e in doc["live"]
    )


def test_short_histories_are_gaps_not_crashes():
    prices, vix = universe()
    prices["XLC"] = prices["XLC"].iloc[-200:]
    del prices["XLRE"]
    doc = ss.build(prices, vix, CFG)
    assert {g["etf"] for g in doc["gaps"]} == {"XLC", "XLRE"}
    assert len(doc["sectors"]) == 9


def test_file_is_plain_json_with_no_nans():
    prices, vix = universe(1500)
    text = json.dumps(ss.build(prices, vix, CFG), allow_nan=False)  # raises on NaN / inf
    assert '"regime_now"' in text


def test_run_writes_the_file_and_keeps_the_old_one_when_the_download_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "out_path", lambda: tmp_path / "sector_signals.json")
    prices, vix = universe(1500)
    monkeypatch.setattr(ss, "fetch", lambda start: (dict(prices), vix))
    assert "sectors" in ss.run()
    before = (tmp_path / "sector_signals.json").read_text()

    def boom(start):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(ss, "fetch", boom)
    with pytest.raises(RuntimeError):
        ss.run()
    assert (tmp_path / "sector_signals.json").read_text() == before


def test_endpoint_serves_the_stored_file_and_empty_before_the_first_run(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from castelino.dashboard.endpoints import dashboards

    monkeypatch.setattr(ss, "out_path", lambda: tmp_path / "sector_signals.json")
    app = FastAPI()
    app.include_router(dashboards.router)
    client = TestClient(app)
    assert client.get("/dashboards/sector-signals").json() == {}
    (tmp_path / "sector_signals.json").write_text('{"as_of": "2026-10-30"}')
    assert client.get("/dashboards/sector-signals").json() == {"as_of": "2026-10-30"}


def test_refresh_job_is_registered_and_skips_when_disabled(monkeypatch):
    from castelino.dashboard.endpoints import refresh

    assert "sector_signals" in refresh._RUNNERS and "sector_signals" in refresh.LABELS

    def disabled():
        raise ss.NothingToDo("disabled")

    monkeypatch.setattr(ss, "run", disabled)
    with pytest.raises(refresh.Skipped):
        refresh.job_sector_signals()
