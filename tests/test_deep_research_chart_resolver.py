import pandas as pd

from castelino.agents.research.deep.chart_resolver import ChartResolver
from castelino.agents.research.deep.models import ChartSpec, ChartType


class FakeOpenBBAdapter:
    """Minimal stand-in for OpenBBAdapter — only the methods the resolver calls."""

    def __init__(self, *, raise_on=None):
        self.raise_on = raise_on or set()

    def history(self, symbol, lookback_days=252):
        if "history" in self.raise_on or symbol == "BAD":
            raise RuntimeError("no data")
        idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
        base = 100.0 if symbol == "AAPL" else 400.0
        return pd.DataFrame({"close": [base, base * 1.1, base * 1.2]}, index=idx)

    def economic_indicators(self, series_ids):
        if "econ" in self.raise_on:
            raise RuntimeError("no series")
        idx = pd.to_datetime(["2026-01-01", "2026-02-01"])
        return pd.DataFrame({series_ids[0]: [3.1, 3.4]}, index=idx)

    def yield_curve(self):
        if "yc" in self.raise_on:
            raise RuntimeError("no curve")
        return pd.DataFrame([{"3M": 4.5, "2Y": 4.2, "10Y": 4.4, "30Y": 4.6}])

    def sector_performance(self):
        return [
            {"sector": "Technology", "change_percent": 1.2},
            {"sector": "Energy", "change_percent": -0.5},
        ]


def _resolver(**kw):
    return ChartResolver(adapter=FakeOpenBBAdapter(**kw))


def test_price_history_maps_to_one_series_of_dates():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.PRICE_HISTORY, title="AAPL 1Y", symbols=["AAPL"]),
    ])
    assert len(out) == 1
    chart = out[0]
    assert chart.type == "price_history"
    assert len(chart.series) == 1
    assert chart.series[0].name == "AAPL"
    assert [p.x for p in chart.series[0].points] == [
        "2026-01-01", "2026-01-02", "2026-01-03"]
    assert chart.series[0].points[0].y == 100.0


def test_comparison_normalizes_to_100_at_t0():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.COMPARISON, title="AAPL vs MSFT",
                  symbols=["AAPL", "MSFT"]),
    ])
    chart = out[0]
    assert {s.name for s in chart.series} == {"AAPL", "MSFT"}
    for s in chart.series:
        assert s.points[0].y == 100.0
        assert round(s.points[2].y, 1) == 120.0  # +20% in both fake series


def test_econ_indicator_maps_series_id():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.ECON_INDICATOR, title="US CPI", series_id="CPIAUCSL"),
    ])
    chart = out[0]
    assert chart.series[0].name == "CPIAUCSL"
    assert [p.y for p in chart.series[0].points] == [3.1, 3.4]


def test_yield_curve_x_is_maturity():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.YIELD_CURVE, title="UST curve"),
    ])
    chart = out[0]
    xs = [p.x for p in chart.series[0].points]
    assert xs == ["3M", "2Y", "10Y", "30Y"]  # preserves column order


def test_bad_ticker_is_rejected_and_chart_dropped():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.PRICE_HISTORY, title="bad", symbols=["not a ticker!!"]),
    ])
    assert out == []  # sanitizer rejects, no data, dropped


def test_fetch_error_drops_only_that_chart():
    out = _resolver(raise_on={"history"}).resolve_all([
        ChartSpec(type=ChartType.PRICE_HISTORY, title="x", symbols=["AAPL"]),
        ChartSpec(type=ChartType.YIELD_CURVE, title="curve"),
    ])
    titles = [c.title for c in out]
    assert titles == ["curve"]  # price dropped, curve survived


def test_max_charts_cap_respected():
    from castelino.config import get_settings

    get_settings().deep_research.max_charts = 1
    try:
        out = _resolver().resolve_all([
            ChartSpec(type=ChartType.YIELD_CURVE, title="a"),
            ChartSpec(type=ChartType.YIELD_CURVE, title="b"),
        ])
        assert len(out) == 1
    finally:
        get_settings().deep_research.max_charts = 4  # restore
