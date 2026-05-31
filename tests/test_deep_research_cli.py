from datetime import UTC, datetime

from typer.testing import CliRunner

from castelino.agents.research.deep.models import (
    DeepResearchReport,
    ResearchSession,
    ResearchStatus,
    SourceRef,
)
from castelino.orchestrator.cli import app


def test_research_command_no_clarify(monkeypatch):
    def fake_run_sync(self, query, *, answers=None):
        return ResearchSession(
            id="x", original_query=query, reworded_query="Q?",
            status=ResearchStatus.COMPLETE,
            report=DeepResearchReport(
                exec_summary="THE ANSWER", confidence=0.8,
                sources=[SourceRef(title="t", url="https://u")],
            ),
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        "castelino.agents.research.deep.orchestrator.DeepResearchOrchestrator.run_sync",
        fake_run_sync,
    )
    result = CliRunner().invoke(app, ["research", "will the fed cut", "--no-clarify"])
    assert result.exit_code == 0
    assert "THE ANSWER" in result.stdout
    assert "https://u" in result.stdout
