"""Number guard for the Weekly Deep Dive: every %, bp or pp figure must be among the numbers of
the facts that part of the report cites (title/subtitle/watch and challenge answers: any fact).
Exhibit picks are checked too: the chart form must fit its facts, and every bar value must be one
of the numbers of the fact it names, so a chart can never plot a figure no source gave."""

from __future__ import annotations

from castelino.agents.update.guard import _supported, unsupported
from castelino.agents.update.models import Fact
from castelino.agents.weekly.models import ExhibitPick, TrendSection, WeeklyReport

PARTS = ("what_happened", "why", "under_the_surface", "market_impact", "watch")


def section_texts(s: TrendSection) -> list[str]:
    return [s.title, *(t for part in PARTS for t in getattr(s, part))]


def report_texts(r: WeeklyReport) -> list[str]:
    out = [r.title, r.subtitle, r.watch]
    out += [t for b in r.bullets for t in (b.lead, b.body)]
    for s in r.sections:
        out += section_texts(s)
        out += [t for c in s.challenges for t in (c.question, c.answer, c.verdict)]
        out += [ex.title for ex in s.exhibits]
    return out


def _has_series(f: Fact | None, kind: str = "daily") -> bool:
    return f is not None and f.series is not None and f.series.kind == kind


def _pick_errors(ex: ExhibitPick, s: TrendSection, by: dict[str, Fact]) -> list[str]:
    errs: list[str] = []
    ids = ex.fact_ids + [p.fact_id for p in ex.points]
    errs += [
        f"exhibit {i} is not one of its facts" for i in dict.fromkeys(ids) if i not in s.fact_ids
    ]
    if ex.kind in ("line", "compare") and not 5 <= ex.window_days <= 3650:
        errs.append(f"exhibit window {ex.window_days} days is out of range")
    if ex.kind == "line" and not (len(ex.fact_ids) == 1 and _has_series(by.get(ex.fact_ids[0]))):
        errs.append(f"exhibit {ex.fact_ids[0] if ex.fact_ids else '?'} has no chartable series")
    elif ex.kind == "compare" and not (
        2 <= len(ex.fact_ids) <= 4 and all(_has_series(by.get(i)) for i in ex.fact_ids)
    ):
        errs.append("compare needs 2-4 facts with a series")
    elif ex.kind == "release" and not (
        len(ex.fact_ids) == 1 and _has_series(by.get(ex.fact_ids[0]), "release")
    ):
        errs.append("release needs one fact with a release history")
    elif ex.kind in ("breakdown", "movers") and not 2 <= len(ex.points) <= 12:
        errs.append(f"{ex.kind} needs 2-12 points")
    elif ex.kind == "dumbbell" and len(ex.points) != 2:
        errs.append("dumbbell needs exactly 2 points")
    for p in ex.points:
        nums = set(by[p.fact_id].numbers) if p.fact_id in by else set()
        decimals = len(f"{p.value:g}".split(".")[1]) if "." in f"{p.value:g}" else 0
        if not _supported(p.value, decimals, True, nums):
            errs.append(f"exhibit point {p.label}={p.value:g} is not a number of {p.fact_id}")
    return errs


def check_report(
    report: WeeklyReport, facts: list[Fact], *, sections: tuple[int, int] = (10, 12)
) -> list[str]:
    by = {f.id: f for f in facts}
    every = {n for f in facts for n in f.numbers}
    errs: list[str] = []

    def nums(ids: list[str], where: str) -> set[float]:
        errs.extend(f"{where}: unknown fact {i}" for i in ids if i not in by)
        return {n for i in ids if i in by for n in by[i].numbers}

    lo, hi = sections
    n_sec, n_bul = len(report.sections), len(report.bullets)
    if not lo <= n_sec <= hi:
        errs.append(f"need {lo} to {hi} sections, got {n_sec}")
    if n_bul != n_sec:
        errs.append(f"need one bullet per section: {n_bul} bullets, {n_sec} sections")
    for k, b in enumerate(report.bullets, 1):
        n = nums(b.fact_ids, f"bullet {k}")
        errs += [f"bullet {k}: {t}" for t in unsupported([b.lead, b.body], n)]
    errs += [
        f"title/subtitle/watch: {t}"
        for t in unsupported([report.title, report.subtitle, report.watch], every)
    ]
    for k, s in enumerate(report.sections, 1):
        n = nums(s.fact_ids, f"section {k}")
        errs += [f"section {k}: {t}" for t in unsupported(section_texts(s), n)]
        for ex in s.exhibits:
            errs += [f"section {k}: {e}" for e in _pick_errors(ex, s, by)]
            errs += [f"section {k} exhibit title: {t}" for t in unsupported([ex.title], n)]
        errs += [
            f"section {k} challenge: {t}"
            for t in unsupported(
                [x for c in s.challenges for x in (c.question, c.answer, c.verdict)], every
            )
        ]
    return errs
