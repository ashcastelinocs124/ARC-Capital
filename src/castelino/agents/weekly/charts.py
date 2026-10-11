"""Weekly exhibits: one series per exhibit, over the window the Editor chose."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from castelino.agents.update.charts import _render, default_fetch
from castelino.agents.update.models import Fact
from castelino.agents.weekly.models import WeeklyExhibit, WeeklyReport

log = logging.getLogger(__name__)

_LABELS = (
    (10, "last week"),
    (35, "last month"),
    (100, "last 3 months"),
    (200, "last 6 months"),
    (400, "last year"),
)


def window_label(days: int) -> str:
    for limit, label in _LABELS:
        if days <= limit:
            return label
    return f"last {round(days / 365)} years"


def make_weekly_exhibits(
    report: WeeklyReport, facts: list[Fact], out_dir: Path, fetch=default_fetch
) -> list[WeeklyExhibit]:
    by = {f.id: f for f in facts}
    out: list[WeeklyExhibit] = []
    for si, sec in enumerate(report.sections):
        for pick in sec.exhibits:
            fact = by.get(pick.fact_id)
            try:
                if fact is None or fact.series is None:
                    raise ValueError("no chartable series")
                ref = fact.series
                release = ref.kind == "release"
                if release:
                    pts = [(p.label, p.value) for p in ref.points]
                else:
                    pts = fetch(ref, pick.window_days)
                if len(pts) < 2:
                    raise ValueError(f"only {len(pts)} point(s)")
                n = len(out) + 1
                # Polymarket history only comes as the last week of daily points
                label = (
                    "last 7 days"
                    if ref.provider == "polymarket"
                    else window_label(pick.window_days)
                )
                shim = SimpleNamespace(
                    id=fact.id, agent="", series=ref, source_title=fact.source_title
                )
                ex = _render(
                    n,
                    shim,
                    pts,
                    Path(out_dir) / f"exhibit_{n}.png",
                    kicker="WEEKLY DEEP DIVE",
                    window_label=None if release else label,
                )
                out.append(
                    WeeklyExhibit(
                        n=n,
                        section=si,
                        fact_id=fact.id,
                        title=ex.title,
                        subtitle=ex.subtitle,
                        file=ex.file,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — a chart is never load-bearing
                log.warning("weekly exhibit %s dropped: %s", pick.fact_id, exc)
    return out
