"""A point's visual: a chart of its numbers (charts.py) or a diagram of how its ideas relate (diagrams.py).

The analyst's own words decide when they name one ("with a diagram", "chart it"). Otherwise one Decisions
API call per point (agents/trade/decide.predicates) asks whether a diagram explains it better: a definition,
the kinds of something, steps or a mechanism with several technical parts (user ask, 2026-10-21). A diagram
that fails its checks falls back to a chart, and a point that gets neither keeps none.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from castelino.agents.research.deep import charts, diagrams
from castelino.agents.research.deep.models import Fact, Point
from castelino.agents.trade import decide, llm

QUESTION = {  # tested on the continual-learning report, 2026-10-21: definitions 0.84-0.95, figure points 0.00-0.17
    "diagram": (
        "A reader understands this point best through a diagram of how its ideas relate: what something is, "
        "its kinds or parts, the steps of a process, or how a mechanism works. Answer no when the point is "
        "mainly about figures: how much, how fast, how they compare or how they changed, which a chart shows best."
    )
}
PROMPT = QUESTION["diagram"]  # shown on /admin → Agents
_DIAGRAM = re.compile(r"\bdiagrams?\b|\bflow ?chart\b|\bschematic\b", re.I)
_CHART = re.compile(r"\bcharts?\b|\bgraphs?\b|\bplots?\b", re.I)


def wanted(ask: str) -> str | None:
    """ "diagram" or "chart" when the analyst named one ("with a visual" names neither), else None."""
    if _DIAGRAM.search(ask or ""):
        return "diagram"
    return "chart" if _CHART.search(ask or "") else None


def _picks_diagram(p: Point, meter: llm.Meter) -> bool:
    text = f"Point: {p.headline}\n{p.body}"
    try:
        return decide.predicates(text, QUESTION, meter, agent="research_visual")["diagram"] >= 0.5
    except Exception:  # noqa: BLE001 - the fallback failed too: a chart, as before
        return False


def visualize(
    points: list[Point], by: dict[str, Fact], meter: llm.Meter, ask: str = ""
) -> list[Point]:
    """The points, each with a chart or a diagram (or neither when nothing fits)."""
    want = wanted(ask)
    if want or not points:
        diag = {p.id for p in points} if want == "diagram" else set()
    else:
        with ThreadPoolExecutor(4) as ex:
            diag = {
                p.id
                for p, d in zip(
                    points, ex.map(lambda p: _picks_diagram(p, meter), points), strict=True
                )
                if d
            }
    drawn = diagrams.diagram_points([p for p in points if p.id in diag], by, meter)
    plotted = charts.chart_points([p for p in points if p.id not in drawn], by, meter)
    return [
        p.model_copy(update={"diagram": drawn.get(p.id), "chart": plotted.get(p.id)})
        for p in points
    ]
