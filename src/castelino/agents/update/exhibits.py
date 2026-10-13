"""Morning Note exhibits: each item's chart in the form the Editor picked, drawn by code.

Forms: line, compare, movers, bars and dumbbell reuse the Weekly Deep Dive's renderers; range (where a
price sits between its 52-week low and high), ladder (one asset across horizons, in order),
columns (a release's last readings, the current streak in green) and vs_expected (actual next to
the estimate) are drawn here. Every plotted number is a fact's number or a fact's fetched series
(`guard.pick_errors` checks the pick first). An item whose pick can't be drawn falls back to the
line chart of its `chart` finding, as before.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from castelino.agents.update.background import _streak
from castelino.agents.update.charts import GREEN, INK, INK2, SLATE, _render, default_fetch, is_rate
from castelino.agents.update.models import Exhibit, Fact, Finding, ItemExhibit, MorningNote
from castelino.agents.weekly.charts import (
    RED,
    _bars,
    _compare,
    _dumbbell,
    _fmt,
    _frame,
    compare_frame,
    default_series,
    window_label,
)

log = logging.getLogger(__name__)
KICKER = "MORNING NOTE"


def _range(ex: ItemExhibit):
    lo_p, last_p, hi_p = ex.points
    lo, last, hi = lo_p.value, last_p.value, hi_p.value

    def draw(ax):
        ax.barh([0], [hi - lo], left=lo, height=0.3, color="#D1FAE5")
        ax.barh([0], [last - lo], left=lo, height=0.3, color=GREEN)
        ax.plot([last, last], [-0.3, 0.3], color=INK, lw=2.2)
        ax.annotate(
            f"{last_p.label} {_fmt(last, ex.unit, signed=False)}",
            (last, 0.3),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=11,
            fontweight="bold",
        )
        for v, p, ha in ((lo, lo_p, "left"), (hi, hi_p, "right")):
            ax.annotate(
                f"{p.label} {_fmt(v, ex.unit, signed=False)}",
                (v, -0.3),
                xytext=(0, -16),
                textcoords="offset points",
                ha=ha,
                fontsize=9.5,
                color=INK2,
            )
        pad = (hi - lo) * 0.04 or 1
        ax.set_xlim(lo - pad, hi + pad)
        ax.set_ylim(-1, 1)
        ax.axis("off")

    where = (last - lo) / (hi - lo) * 100 if hi > lo else 100
    return draw, f"{last_p.label} sits {where:.0f}% of the way from {lo_p.label} to {hi_p.label}"


def _columns(fact: Fact):
    pts = fact.series.points
    vals = [p.value for p in pts]
    n, direction = _streak(vals)
    lit = set(range(len(vals) - max(n, 1), len(vals)))

    def draw(ax):
        x = list(range(len(vals)))
        bars = ax.bar(x, vals, color=[GREEN if i in lit else SLATE for i in x], width=0.65)
        for i, (b, v) in enumerate(zip(bars, vals, strict=True)):
            if i in lit:
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    v,
                    f"{v:.2f}%".replace(".00%", "%"),
                    ha="center",
                    va="bottom" if v >= 0 else "top",
                    fontsize=8.5,
                    fontweight="bold",
                )
        ax.set_xticks(x)
        ax.set_xticklabels([p.label for p in pts], fontsize=7.5)
        ax.axhline(0, color=INK2, lw=1)
        top = max(max(vals), 0)
        ax.set_ylim(min(min(vals), 0) * 1.15, top * 1.15 or 1)

    if n >= 2:
        sub = f"{fact.series.label}, %: {n} straight {direction}s to {vals[-1]:.2f}%"
    else:
        sub = f"{fact.series.label}, %: last {len(vals)} readings"
    return draw, sub


def _vs_expected(ex: ItemExhibit):
    exp, act = ex.points
    beat = act.value >= exp.value

    def draw(ax):
        ax.bar([0], [exp.value], width=0.5, color="white", edgecolor=INK2, ls="--", lw=1.5)
        ax.bar([1], [act.value], width=0.5, color=GREEN if beat else RED)
        for x, p in ((0, exp), (1, act)):
            ax.text(
                x,
                p.value,
                _fmt(p.value, ex.unit, signed=False),
                ha="center",
                va="bottom" if p.value >= 0 else "top",
                fontsize=10.5,
                fontweight="bold",
            )
        ax.set_xticks([0, 1])
        ax.set_xticklabels([exp.label, act.label], fontsize=9.5)
        ax.axhline(0, color=INK2, lw=1)
        lo, hi = min(exp.value, act.value, 0), max(exp.value, act.value, 0)
        ax.set_ylim(lo * 1.2, hi * 1.2 or 1)

    if ex.unit in ("%", "pp", "bp"):
        gap = f"{abs(act.value - exp.value):.2f}{'pp' if ex.unit == '%' else ex.unit}"
    else:
        gap = f"{abs(act.value / exp.value - 1) * 100:.1f}%" if exp.value else ""
    return draw, f"{act.label} {'beat' if beat else 'missed'} {exp.label} by {gap}"


def draw_pick(
    n: int,
    ex: ItemExhibit,
    by: dict[str, Fact],
    path: Path,
    fetch=default_fetch,
    series=default_series,
) -> tuple[str, str]:
    """Draw one pick to `path`; returns (title, subtitle). Raises when it can't be drawn."""
    cited = [by[i] for i in dict.fromkeys(ex.fact_ids + [p.fact_id for p in ex.points])]
    data = ", ".join(dict.fromkeys(f.source_title for f in cited)) + "."
    title = ex.title
    if ex.kind == "line":
        fact = by[ex.fact_ids[0]]
        pts = fetch(fact.series, ex.window_days)
        if len(pts) < 2:
            raise ValueError(f"only {len(pts)} point(s)")
        shim = SimpleNamespace(
            id=fact.id, agent="", series=fact.series, source_title=fact.source_title
        )
        e = _render(n, shim, pts, path, kicker=KICKER, window_label=window_label(ex.window_days))
        return e.title.removeprefix(f"Exhibit {n}: "), e.subtitle
    if ex.kind == "compare":
        facts = [by[i] for i in ex.fact_ids]
        df = compare_frame(facts, ex.window_days, series)
        rebased = not all(f.series.provider == "fred" and is_rate(f.series.id) for f in facts)
        draw, sub = _compare(df, rebased)
        sub = f"{sub} · {window_label(ex.window_days)}"
        kw = {}
    elif ex.kind == "columns":
        draw, sub = _columns(by[ex.fact_ids[0]])
        kw = {"bottom": 0.24}
    elif ex.kind in ("movers", "bars", "ladder"):
        draw, sub = _bars(
            ex, diverging=False, keep_order=ex.kind == "ladder", signed=ex.kind != "bars"
        )
        kw = {"left": 0.26, "bottom": 0.14}
    elif ex.kind == "dumbbell":
        draw, sub = _dumbbell(ex)
        kw = {}
    elif ex.kind == "range":
        draw, sub = _range(ex)
        kw = {"bottom": 0.16}
    elif ex.kind == "vs_expected":
        draw, sub = _vs_expected(ex)
        kw = {}
    else:
        raise ValueError(f"unknown form {ex.kind}")
    _frame(n, title, sub, data, path, draw, kicker=KICKER, **kw)
    return title, sub


def make_note_exhibits(
    note: MorningNote,
    findings: list[Finding],
    facts: list[Fact],
    out_dir: Path,
    fetch=default_fetch,
    series=default_series,
) -> list[Exhibit]:
    by = {f.id: f for f in facts}
    find_by = {f.id: f for f in findings}
    out: list[Exhibit] = []
    for it in sorted(note.items, key=lambda i: i.rank):
        n = len(out) + 1
        path = Path(out_dir) / f"exhibit_{n}.png"
        anchor = it.chart or (it.finding_ids[0] if it.finding_ids else "")
        if it.exhibit is not None:
            try:
                title, sub = draw_pick(n, it.exhibit, by, path, fetch, series)
                out.append(
                    Exhibit(
                        n=n,
                        finding_id=anchor,
                        item=it.rank,
                        title=f"Exhibit {n}: {title}",
                        subtitle=sub,
                        file=path.name,
                    )
                )
                continue
            except Exception as exc:  # noqa: BLE001 — a chart is never load-bearing
                log.warning("item %s %s chart dropped: %s", it.rank, it.exhibit.kind, exc)
        f = find_by.get(it.chart or "")
        if f is None or f.series is None:
            continue
        try:
            ref = f.series
            pts = [(p.label, p.value) for p in ref.points] if ref.kind == "release" else fetch(ref)
            if len(pts) < 2:
                raise ValueError(f"only {len(pts)} point(s)")
            e = _render(n, f, pts, path)
            out.append(e.model_copy(update={"item": it.rank}))
        except Exception as exc:  # noqa: BLE001
            log.warning("chart for %s dropped: %s", f.id, exc)
    return out
