"""Deep Lead: reads the week's Morning Notes, picks the trends, and staffs the desk."""

from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.agents.weekly.models import DeepPlan
from castelino.config import get_settings

SYSTEM = """You lead ARC Research's Weekly Deep Dive. You get the week's Morning Notes (headlines,
takeaways, items and findings) and the desk's memory themes.
1. Pick the 3-4 trends of the week that mattered most for a US macro investor: stories that moved
   markets or built across several days. For each: a short title and one line on why it mattered.
2. Staff a desk of at most {max_agents} specialist sub-agents to research them. Each gets:
   - name: a desk name, e.g. "Rates desk"
   - description: what the desk covers
   - goal: what to establish with data this week, e.g. "explain why 10y yields rose; separate
     term premium from Fed repricing"
   - tools: only the ones it needs, from fred_series, yahoo_prices, bls_series, polymarket_odds,
     web_search
   - related: names of other desks whose work overlaps (they share a board), or []
One desk may cover two related trends. Prefer data tools for anything measurable."""


class DeepLead(StructuredAgent[DeepPlan]):
    name = "deep_lead"
    output_schema = DeepPlan
    tier = "reasoning"

    def __init__(self) -> None:
        cfg = get_settings().deep_dive
        self.model = cfg.lead_model
        self.max_output_tokens = cfg.max_output_tokens
        self.max_agents = cfg.max_agents

    def system_prompt(self) -> str:
        return SYSTEM.format(max_agents=self.max_agents)

    def user_prompt(self, *, week: str, week_md: str, memory_md: str) -> str:
        return (
            f"# Week {week}\n\n## Morning Notes\n{week_md}\n\n"
            f"## Memory themes\n{memory_md or '(empty)'}"
        )


def validate_plan(plan: DeepPlan, max_agents: int) -> DeepPlan:
    seen: set[str] = set()
    agents = []
    for a in plan.agents:
        key = a.name.strip().lower()
        if not key or key in seen or not a.tools:
            continue
        seen.add(key)
        agents.append(a)
    agents = agents[:max_agents]
    names = {a.name for a in agents}
    agents = [
        a.model_copy(
            update={
                "related": [r for r in dict.fromkeys(a.related) if r in names and r != a.name],
                "tools": list(dict.fromkeys(a.tools)),
            }
        )
        for a in agents
    ]
    if not agents:
        raise RuntimeError("lead staffed no usable sub-agents")
    if not plan.trends:
        raise RuntimeError("lead picked no trends")
    return DeepPlan(trends=plan.trends[:4], agents=agents)


def plan(week: str, week_md: str, memory_md: str) -> DeepPlan:
    lead = DeepLead()
    return validate_plan(lead(week=week, week_md=week_md, memory_md=memory_md), lead.max_agents)
