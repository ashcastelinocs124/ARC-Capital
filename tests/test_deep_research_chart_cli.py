from datetime import UTC, datetime

from typer.testing import CliRunner

from castelino.agents.research.deep.models import (
    ChartPoint,
    ChartSeries,
    ChartType,
    DeepResearchReport,
    ResearchSession,
    ResearchStatus,
    ResolvedChart,
)
from castelino.orchestrator.cli import app


def test_cli_prints_chart_list(monkeypatch):
    now = datetime.now(UTC)
    report = DeepResearchReport(
        exec_summary="Apple looks strong.",
        charts=[ResolvedChart(
            type=ChartType.PRICE_HISTORY, title="AAPL — 1Y price",
            rationale="momentum",
            series=[ChartSeries(name="AAPL",
                                points=[ChartPoint(x="2026-01-01", y=1.0),
                                        ChartPoint(x="2026-01-02", y=2.0)])],
        )],
    )
    sess = ResearchSession(id="x", original_query="apple",
                           status=ResearchStatus.COMPLETE, report=report,
                           created_at=now, updated_at=now)

    def fake_run_sync(self, query, answers=None):
        return sess

    monkeypatch.setattr(
        "castelino.agents.research.deep.orchestrator.DeepResearchOrchestrator.run_sync",
        fake_run_sync,
    )
    res = CliRunner().invoke(app, ["research", "apple", "--no-clarify"])
    assert res.exit_code == 0
    assert "Supporting charts" in res.stdout
    assert "AAPL — 1Y price" in res.stdout
    assert "price_history" in res.stdout
    assert "momentum" in res.stdout
