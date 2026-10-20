"""Chart agent (gpt-6-luna): one call charts every point from the facts that point cites: bars to compare, a
line over time, or before -> after. Every chart has at least 2 values: a single figure is never charted. Code
checks every value is one of its fact's numbers and retries once with the errors; a point that still fails,
or has fewer than 2 comparable figures, gets no chart. A chart never changes the text, and a chart failure
never fails the run."""

from __future__ import annotations

import math

from castelino.agents.research.deep.models import (
    ChartSet,
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
  earlier first, and they must differ). Never chart a single figure: put the headline figure beside the facts' figures for the
  same measure in other groups, years or sources, and use as many as the facts hold (3 or more where they
  can). A point whose facts hold fewer than 2 comparable figures gets no chart: leave it out.
- values: each is {fact_id, label, value}. value must be one of that fact's listed numbers, copied exactly;
  fact_id must be one of the point's facts. Never compute, convert or round a number, and never plot a year.
- One measure per chart, all values in one unit: %, $, bp, pp, level or "". Bars compare things of one
  kind (all sectors, or all countries, or all firm sizes), never a mix.
- title: what is measured, and where or when, in at most 10 plain words; no dashes.
Chart the figures the point's headline is about."""
SIZES = {"bars": (2, 10), "line": (3, 10), "dumbbell": (2, 2)}


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
    errs = (
        []
        if lo <= len(c.values) <= hi
        else [f"{point.id}: {c.form} needs {lo}-{hi} values, got {len(c.values)}"]
    )
    if c.form == "dumbbell" and len({v.value for v in c.values}) == 1:
        errs.append(f"{point.id}: the dumbbell's two values are equal, so it draws one dot")
    for v in c.values:
        if v.fact_id not in point.fact_ids or v.fact_id not in by:
            errs.append(f"{point.id}: {v.fact_id} is not one of this point's facts")
        elif not any(math.isclose(v.value, n, abs_tol=1e-9) for n in by[v.fact_id].numbers):
            errs.append(f"{point.id}: {v.value} is not a number of {v.fact_id}")
    return errs


def _ask(msgs: list[dict], meter: llm.Meter) -> ChartSet:
    cfg = get_settings().deep_research
    try:
        return llm.structured("research_charter", cfg.chart_model, msgs, ChartSet, meter)
    except Exception:  # noqa: BLE001 - a chart is never load-bearing; the point goes without one
        return ChartSet(charts=[])


def chart_points(
    points: list[Point], by: dict[str, Fact], meter: llm.Meter
) -> dict[str, PointChart]:
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
        fix = (
            "Fix only these points' charts and return them; leave out a point whose facts hold "
            "fewer than 2 comparable figures:\n" + "\n".join(e for es in errs.values() for e in es)
        )
        take(
            _ask(
                [
                    *msgs,
                    {"role": "assistant", "content": out.model_dump_json()},
                    {"role": "user", "content": fix},
                ],
                meter,
            )
        )
    return done
