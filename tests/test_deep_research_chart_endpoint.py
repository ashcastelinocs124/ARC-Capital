from datetime import UTC, datetime

from fastapi.testclient import TestClient

import castelino.dashboard.endpoints.deep_research as dr
from castelino.agents.research.deep.models import (
    ChartPoint,
    ChartSeries,
    ChartType,
    DeepResearchReport,
    ResearchSession,
    ResearchStatus,
    ResolvedChart,
)
from castelino.agents.research.deep.store import ResearchStore
from castelino.dashboard.main import app


def test_report_charts_serialize_in_get(tmp_path):
    dr._store_root = tmp_path
    store = ResearchStore(root=tmp_path)
    now = datetime.now(UTC)
    sess = ResearchSession(
        id="abc123", original_query="q", status=ResearchStatus.COMPLETE,
        created_at=now, updated_at=now,
        report=DeepResearchReport(
            exec_summary="ok",
            charts=[ResolvedChart(
                type=ChartType.PRICE_HISTORY, title="AAPL",
                series=[ChartSeries(name="AAPL",
                                    points=[ChartPoint(x="2026-01-01", y=190.0)])],
            )],
        ),
    )
    store.save(sess)

    try:
        client = TestClient(app)
        r = client.get("/research/abc123")
        assert r.status_code == 200
        body = r.json()
        charts = body["report"]["charts"]
        assert len(charts) == 1
        assert charts[0]["type"] == "price_history"
        assert charts[0]["series"][0]["points"][0]["y"] == 190.0
    finally:
        dr._store_root = None  # restore
