import pytest
from pydantic import ValidationError

from castelino.agents.weekly.models import (
    DeepPlan,
    RegimeRead,
    RunCounts,
    SubAgentSpec,
    Trend,
    WeeklyRecord,
    WeeklyReport,
)
from castelino.config import get_settings


def test_deep_dive_config_defaults():
    dd = get_settings().deep_dive
    assert (dd.lead_model, dd.agent_model, dd.editor_model) == (
        "gpt-6-sol",
        "gpt-6-luna",
        "claude-opus-5-5",
    )
    assert (dd.max_agents, dd.max_tool_calls, dd.max_grill_rounds) == (4, 12, 2)
    assert dd.editor_effort == "high" and dd.data_dir == "data/deep"


def test_anthropic_key_missing_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _ = get_settings().anthropic_api_key


def test_unknown_tool_rejected():
    with pytest.raises(ValidationError):
        SubAgentSpec(name="X", description="d", goal="g", tools=["shell"], related=[])


def test_record_round_trips():
    plan = DeepPlan(
        trends=[Trend(title="t", why="w")],
        agents=[
            SubAgentSpec(
                name="Rates desk", description="d", goal="g", tools=["fred_series"], related=[]
            )
        ],
    )
    rec = WeeklyRecord(
        week="2026-W41",
        start="2026-10-05",
        end="2026-10-09",
        generated_at="2026-10-11T06:40:00",
        plan=plan,
        findings=[],
        facts=[],
        board=[],
        grill_log=[],
        report=WeeklyReport(title="T", subtitle="S", bullets=[], watch="W", sections=[]),
        exhibits=[],
        scorecard=[],
        regime=RegimeRead(),
        counts=RunCounts(),
        data_gaps=[],
        models={"lead": "gpt-6-sol"},
    )
    assert WeeklyRecord.model_validate_json(rec.model_dump_json()) == rec
    assert rec.version == 1
