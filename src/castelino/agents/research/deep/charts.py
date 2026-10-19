"""Chart agent (gpt-6-luna): one call charts every point from the facts that point cites: bars to compare, a
line over time, before -> after, or a big-number tile. Code checks every value is one of its fact's numbers
and retries once with the errors; a point that still fails gets a code-made tile of the first figure its text
states. A chart never changes the text, and a chart failure never fails the run."""

from __future__ import annotations

import math
import re

from castelino.agents.research.deep.models import (
    ChartSet,
    ChartValue,
    Point,
    PointChart,
    PointChartDraft,
)
from castelino.agents.trade import llm
from castelino.agents.update.models import Fact
from castelino.config import get_settings

SYSTEM = """You chart the points of an ARC Research report. For each point you get its headline, body and
the facts it cites, each with the numbers it holds. Return one chart per point, using only those facts:
- form: bars to compare 2 to 10 things (labels name the things), line for one measure over 3 to 10 dates
  in time order (labels are the dates), dumbbell for one measure before and after (exactly 2 values,
  earlier first), stat for a single headline figure (exactly 1 value).
- values: each is {fact_id, label, value}. value must be one of that fact's listed numbers, copied exactly;
  fact_id must be one of the point's facts. Never compute, convert or round a number, and never plot a year.
- One measure per chart, all values in one unit: %, $, bp, pp, level or "".
- title: what is measured, and where or when, in at most 10 plain words; no dashes.
Chart the figures the point's headline is about."""
SIZES = {"bars": (2, 10), "line": (3, 10), "dumbbell": (2, 2), "stat": (1, 1)}
# a figure in the point's text, with its unit when it has one: "69%", "12 percent", "25 bp", "3.5"
_FIG = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(%|percent|pp|bp)?", re.I)


def _brief(points: list[Point], by: dict[str, Fact]) -> str:
    parts = []
    for p in points:
        facts = "\n".join(
            f"[{i}] {by[i].text} | numbers: {', '.join(f'{n:g}' for n in by[i].numbers)}"
            for i in p.fact_ids
            if i in by
        )
        parts.append(f"## {p.id}\nHeadline: {p.headline}\nBody: {p.body}\nFacts:\n{facts}")
    return "\n\n".join(parts)


def chart_errors(c: PointChartDraft, point: Point, by: dict[str, Fact]) -> list[str]:
    lo, hi = SIZES[c.form]
    errs = [] if lo <= len(c.values) <= hi else [f"{point.id}: {c.form} needs {lo}-{hi} values, got {len(c.values)}"]
    for v in c.values:
        if v.fact_id not in point.fact_ids or v.fact_id not in by:
            errs.append(f"{point.id}: {v.fact_id} is not one of this point's facts")
        elif not any(math.isclose(v.value, n, abs_tol=1e-9) for n in by[v.fact_id].numbers):
            errs.append(f"{point.id}: {v.value} is not a number of {v.fact_id}")
    return errs


def tile(point: Point, by: dict[str, Fact]) -> PointChart | None:
    """The first figure the point's text states that a cited fact also holds: unit figures first, never a year."""
    found = [(m.group(2) or "", float(m.group(1))) for m in _FIG.finditer(f"{point.headline} {point.body}")]
    ranked = [f for f in found if f[0]] + [f for f in found if not f[0] and not 1900 <= f[1] <= 2100]
    for unit, n in ranked:
        for i in point.fact_ids:
            if i in by and any(math.isclose(n, x, abs_tol=1e-9) for x in by[i].numbers):
                u = "%" if unit.lower() in ("%", "percent") else unit.lower()
                label = by[i].text if len(by[i].text) <= 80 else by[i].text[:79] + "…"
                return PointChart(
                    form="stat",
                    title=point.headline,
                    unit=u,
                    values=[ChartValue(fact_id=i, label=label, value=n)],
                    fallback=True,
                )
    return None


def _ask(msgs: list[dict], meter: llm.Meter) -> ChartSet:
    cfg = get_settings().deep_research
    try:
        return llm.structured("research_charter", cfg.chart_model, msgs, ChartSet, meter)
    except Exception:  # noqa: BLE001 - a chart is never load-bearing; the tile fallback covers it
        return ChartSet(charts=[])


def chart_points(points: list[Point], by: dict[str, Fact], meter: llm.Meter) -> dict[str, PointChart]:
    """A chart per point id; a point with no chartable figure is simply missing from the result."""
    if not points:
        return {}
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _brief(points, by)}]
    out, done, errs = _ask(msgs, meter), {}, {}

    def take(cs: ChartSet) -> None:
        for p in points:
            if p.id in done:
                continue
            c = next((x for x in cs.charts if x.point_id == p.id), None)
            e = chart_errors(c, p, by) if c else [f"{p.id}: no chart returned"]
            if e:
                errs[p.id] = e
            else:
                errs.pop(p.id, None)
                done[p.id] = PointChart(form=c.form, title=c.title, unit=c.unit, values=c.values)

    take(out)
    if errs:
        fix = "Fix only these points' charts and return them:\n" + "\n".join(e for es in errs.values() for e in es)
        take(_ask([*msgs, {"role": "assistant", "content": out.model_dump_json()}, {"role": "user", "content": fix}], meter))
    for p in points:
        if p.id not in done and (t := tile(p, by)):
            done[p.id] = t
    return done
