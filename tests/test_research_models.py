import pytest

from castelino.agents.research.deep.models import (
    Point,
    Proposal,
    ResearchReport,
    ResearchSession,
)
from castelino.config import get_settings
from tests.research_fakes import agent, fact


def test_config_defaults():
    dr = get_settings().deep_research
    assert (dr.max_agents, dr.max_gap_agents, dr.max_tool_calls, dr.gap_rounds) == (8, 4, 12, 1)
    assert dr.agent_model == "deepseek/deepseek-v4.1-flash-1017"
    assert dr.agent_fallback_model == "gpt-6-luna"
    assert dr.writer_model == "claude-opus-5-5" and dr.writer_effort == "high"
    assert dr.revise_model == "anthropic/claude-haiku-5.5"
    assert dr.revise_fallback_model == "anthropic/claude-sonnet-5.5"
    assert dr.revise_openai_model == "gpt-6-sol"
    assert (dr.keep_full_days, dr.cost_cap_usd, dr.x_posts_per_report) == (14, 8.0, 100)
    assert dr.data_dir == "data/research"


def _session() -> ResearchSession:
    p = Point(id="p1", agent="A", headline="h", body="b", fact_ids=["A1"])
    return ResearchSession(
        id="s1",
        topic="AI adoption",
        agents=[agent("A"), agent("B", facts=[fact("B1", "27%", [27.0])])],
        board_facts={"B9": fact("B9", "posted", [1.0])},
        report=ResearchReport(title="t", subtitle="s", points=[p]),
        proposals=[Proposal(n=1, point_id="p1", agent="A", text="?", base_version=1, created_at="x")],
        created_at="2026-10-19T10:00:00",
        updated_at="2026-10-19T10:00:00",
    )


def test_fact_map_has_every_agents_facts_and_the_board():
    assert set(_session().fact_map()) == {"A1", "B1", "B9"}


def test_lookups_and_misses():
    s = _session()
    assert s.agent("B").letter == "B" and s.point("p1").id == "p1" and s.proposal(1).n == 1
    for miss in (lambda: s.agent("Z"), lambda: s.point("p9"), lambda: s.proposal(2)):
        with pytest.raises(KeyError):
            miss()
