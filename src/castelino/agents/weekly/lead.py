"""Deep Lead: reads the week's Morning Notes, picks the trends, and staffs the desk."""

from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.agents.weekly.models import DeepPlan
from castelino.config import get_settings

SYSTEM = """You lead ARC Research's Weekly Deep Dive. You get the week's Morning Notes (headlines,
takeaways, items and findings) and the desk's memory themes.
1. Pick the {min_trends}-{max_trends} trends of the week that mattered for a US macro investor:
   stories that moved markets or built across several days, from rates, inflation and labour to
   energy, equities, credit, FX, AI and chips. On a quiet week use smaller stories rather than
   fewer trends. For each: a short title and one line on why it mattered.
2. Staff {max_agents} specialist sub-agents to research them. Each desk owns 2-3 related trends
   and every trend belongs to exactly one desk. Each desk gets:
   - name: a desk name, e.g. "Rates desk"
   - description: what the desk covers
   - goal: what to establish with data this week, across its trends
   - tools: only the ones it needs, from fred_series, yahoo_prices, bls_series, polymarket_odds,
     web_search
   - related: names of other desks whose work overlaps (they share a board), or []
   - trends: the exact titles of the trends it owns
Prefer data tools for anything measurable."""


class ShortPlanError(RuntimeError):
    pass


class DeepLead(StructuredAgent[DeepPlan]):
    name = "deep_lead"
    output_schema = DeepPlan
    tier = "reasoning"

    def __init__(self) -> None:
        cfg = get_settings().deep_dive
        self.model = cfg.lead_model
        self.max_output_tokens = cfg.max_output_tokens
        self.max_agents = cfg.max_agents
        self.min_trends, self.max_trends = cfg.min_trends, cfg.max_trends

    def system_prompt(self) -> str:
        return SYSTEM.format(
            min_trends=self.min_trends, max_trends=self.max_trends, max_agents=self.max_agents
        )

    def user_prompt(self, *, week: str, week_md: str, memory_md: str, retry: str = "") -> str:
        parts = [
            f"# Week {week}",
            f"## Morning Notes\n{week_md}",
            f"## Memory themes\n{memory_md or '(empty)'}",
        ]
        if retry:
            parts.append(f"## Correction\n{retry}")
        return "\n\n".join(parts)


def validate_plan(
    plan: DeepPlan, max_agents: int = 5, min_trends: int = 10, max_trends: int = 12
) -> DeepPlan:
    seen: set[str] = set()
    agents = []
    for a in plan.agents:
        key = a.name.strip().lower()
        if not key or key in seen or not a.tools:
            continue
        seen.add(key)
        agents.append(a)
    agents = agents[:max_agents]
    if not agents:
        raise RuntimeError("lead staffed no usable sub-agents")
    trends = plan.trends[:max_trends]
    if len(trends) < min_trends:
        raise ShortPlanError(f"only {len(trends)} trends; a weekly needs {min_trends}")
    titles = [t.title for t in trends]
    owner: dict[str, str] = {}  # a trend claimed twice stays with its first desk
    for a in agents:
        for t in a.trends:
            if t in titles and t not in owner:
                owner[t] = a.name
    names = {a.name for a in agents}
    owned = {a.name: [t for t in titles if owner.get(t) == a.name] for a in agents}
    for t in titles:  # unowned (e.g. its desk was dropped): give it to the lightest desk
        if t not in owner:
            lightest = min(agents, key=lambda a: len(owned[a.name]))
            owned[lightest.name].append(t)
    agents = [
        a.model_copy(
            update={
                "related": [r for r in dict.fromkeys(a.related) if r in names and r != a.name],
                "tools": list(dict.fromkeys(a.tools)),
                "trends": owned[a.name],
            }
        )
        for a in agents
    ]
    return DeepPlan(trends=trends, agents=agents)


def plan(week: str, week_md: str, memory_md: str) -> DeepPlan:
    lead = DeepLead()
    caps = dict(max_agents=lead.max_agents, min_trends=lead.min_trends, max_trends=lead.max_trends)
    first = lead(week=week, week_md=week_md, memory_md=memory_md)
    try:
        return validate_plan(first, **caps)
    except ShortPlanError as e:  # one retry, naming the shortfall
        retry = f"Your plan had {e}. Pick {lead.min_trends}-{lead.max_trends} trends."
        return validate_plan(
            lead(week=week, week_md=week_md, memory_md=memory_md, retry=retry), **caps
        )
