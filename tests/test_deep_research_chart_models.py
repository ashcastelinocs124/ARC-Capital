from castelino.agents.research.deep.models import (
    ChartPoint,
    ChartSeries,
    ChartSpec,
    ChartType,
    DeepResearchReport,
    ResolvedChart,
)


def test_chart_spec_defaults():
    spec = ChartSpec(type=ChartType.PRICE_HISTORY, title="AAPL 1Y")
    assert spec.type == "price_history"
    assert spec.symbols == []
    assert spec.series_id == ""
    assert spec.lookback_days == 365
    assert spec.rationale == ""


def test_resolved_chart_roundtrip():
    chart = ResolvedChart(
        type=ChartType.PRICE_HISTORY,
        title="AAPL — 1Y price",
        rationale="rate sensitive",
        series=[ChartSeries(name="AAPL", points=[ChartPoint(x="2026-01-01", y=190.0)])],
        y_label="USD",
    )
    assert chart.source == "OpenBB"
    assert chart.series[0].points[0].y == 190.0
    # serializes to JSON cleanly (used by the endpoint)
    dumped = chart.model_dump(mode="json")
    assert dumped["series"][0]["points"][0]["x"] == "2026-01-01"


def test_report_has_charts_field_default_empty():
    rep = DeepResearchReport(exec_summary="hi")
    assert rep.charts == []
