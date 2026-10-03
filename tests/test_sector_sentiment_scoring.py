"""Pure scoring math: z-scores, per-stock scores, sector aggregation."""

import pytest

from castelino.signals.sector_sentiment import (
    SECTOR_ETFS,
    StockRow,
    aggregate_sectors,
    cross_sectional_score,
    score_stocks,
)


def _row(**kw) -> StockRow:
    base = dict(
        symbol="AAA",
        name="A",
        sector="Technology",
        market_cap=1e9,
        rsi14=50.0,
        macd_hist=0.0,
        vs_sma50=0.0,
        vs_sma200=0.0,
        ret_3m=0.0,
        rev_yoy=0.1,
        earnings_growth=0.0,
        pe_rel=1.0,
    )
    base.update(kw)
    return StockRow(**base)


def test_sector_etfs_covers_11_gics():
    assert len(SECTOR_ETFS) == 11
    etfs = {etf for etf, _ in SECTOR_ETFS.values()}
    assert {"XLK", "XLE", "XLF", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"} == etfs


def test_cross_sectional_score_zscores_and_clips():
    scores = cross_sectional_score({"a": 1.0, "b": 2.0, "c": 3.0, "d": None})
    assert "d" not in scores
    assert scores["a"] < scores["b"] < scores["c"]
    assert scores["a"] == pytest.approx(-scores["c"])
    assert all(-1.0 <= v <= 1.0 for v in scores.values())


def test_cross_sectional_score_constant_input_is_zero():
    scores = cross_sectional_score({"a": 5.0, "b": 5.0})
    assert scores == {"a": 0.0, "b": 0.0}


def test_score_stocks_divergence_sign():
    # hot technicals + weak fundamentals -> positive divergence
    hot = _row(symbol="HOT", rsi14=80, vs_sma200=0.3, ret_3m=0.25, rev_yoy=0.0, pe_rel=2.0)
    cold = _row(symbol="COLD", rsi14=30, vs_sma200=-0.15, ret_3m=-0.1, rev_yoy=0.3, pe_rel=0.6)
    mid = _row(symbol="MID")
    out = {r.symbol: r for r in score_stocks([hot, cold, mid])}
    assert out["HOT"].divergence > 0
    assert out["COLD"].divergence < 0
    assert out["HOT"].tech_score > out["COLD"].tech_score


def test_score_stocks_missing_fundamentals_skipped():
    full = _row(symbol="FULL")
    other = _row(symbol="OTHR", rsi14=60)
    nofund = _row(symbol="NOFU", rev_yoy=None, earnings_growth=None, pe_rel=None)
    out = {r.symbol: r for r in score_stocks([full, other, nofund])}
    assert out["NOFU"].fundamentals_missing is True
    assert out["NOFU"].fund_score is None
    assert out["NOFU"].divergence is None
    assert out["NOFU"].tech_score is not None  # technicals still scored


def test_aggregate_sectors_cap_weighted_and_labeled():
    big = _row(symbol="BIG", market_cap=9e9)
    small = _row(symbol="SML", market_cap=1e9)
    rows = score_stocks(
        [
            big,
            small,
            _row(
                symbol="E1",
                sector="Energy",
                rsi14=20,
                vs_sma200=-0.2,
                ret_3m=-0.15,
                rev_yoy=0.4,
                pe_rel=0.5,
            ),
            _row(
                symbol="E2",
                sector="Energy",
                rsi14=25,
                vs_sma200=-0.18,
                ret_3m=-0.12,
                rev_yoy=0.35,
                pe_rel=0.6,
            ),
        ]
    )
    sectors = {s.sector: s for s in aggregate_sectors(rows, euphoric=0.3, fearful=-0.3)}
    tech = sectors["Technology"]
    # cap-weighted: BIG dominates 9:1
    by_sym = {r.symbol: r for r in rows}
    expected = (by_sym["BIG"].divergence * 9 + by_sym["SML"].divergence * 1) / 10
    assert tech.divergence == pytest.approx(expected)
    assert tech.etf == "XLK"
    assert sectors["Energy"].label == "fearful"
    assert sectors["Energy"].divergence <= -0.3


def test_aggregate_skips_stocks_without_divergence():
    ok = _row(symbol="OK1")
    ok2 = _row(symbol="OK2", rsi14=60)
    skip = _row(
        symbol="SKIP",
        market_cap=1e15,
        rev_yoy=None,
        earnings_growth=None,
        pe_rel=None,
    )
    rows = score_stocks([ok, ok2, skip])
    sectors = aggregate_sectors(rows, euphoric=0.3, fearful=-0.3)
    assert len(sectors) == 1  # only Technology, from OK1/OK2
    # SKIP's monster cap must not influence the sector (it was renormalized out)
    assert sectors[0].label in {"euphoric", "fair", "fearful"}
