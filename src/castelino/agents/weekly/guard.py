"""Number guard for the Weekly Deep Dive: every %, bp or pp figure must be among the numbers of
the facts that part of the report cites (title/subtitle/watch and challenge answers: any fact)."""

from __future__ import annotations

from castelino.agents.update.guard import unsupported
from castelino.agents.update.models import Fact
from castelino.agents.weekly.models import WeeklyReport


def report_texts(r: WeeklyReport) -> list[str]:
    out = [r.title, r.subtitle, r.watch]
    out += [t for b in r.bullets for t in (b.lead, b.body)]
    for s in r.sections:
        out += [s.title, *s.paragraphs, *(c.answer for c in s.challenges)]
    return out


def check_report(report: WeeklyReport, facts: list[Fact]) -> list[str]:
    by = {f.id: f for f in facts}
    every = {n for f in facts for n in f.numbers}
    errs: list[str] = []

    def nums(ids: list[str], where: str) -> set[float]:
        errs.extend(f"{where}: unknown fact {i}" for i in ids if i not in by)
        return {n for i in ids if i in by for n in by[i].numbers}

    if not 2 <= len(report.sections) <= 4:
        errs.append(f"need 2 to 4 sections, got {len(report.sections)}")
    if not report.bullets:
        errs.append("need at least one bullet")
    for k, b in enumerate(report.bullets, 1):
        n = nums(b.fact_ids, f"bullet {k}")
        errs += [f"bullet {k}: {t}" for t in unsupported([b.lead, b.body], n)]
    errs += [
        f"title/subtitle/watch: {t}"
        for t in unsupported([report.title, report.subtitle, report.watch], every)
    ]
    for k, s in enumerate(report.sections, 1):
        n = nums(s.fact_ids, f"section {k}")
        errs += [f"section {k}: {t}" for t in unsupported([s.title, *s.paragraphs], n)]
        for ex in s.exhibits:
            if ex.fact_id not in s.fact_ids:
                errs.append(f"section {k}: exhibit {ex.fact_id} is not one of its facts")
            elif by.get(ex.fact_id) is None or by[ex.fact_id].series is None:
                errs.append(f"section {k}: exhibit {ex.fact_id} has no chartable series")
            if not 5 <= ex.window_days <= 3650:
                errs.append(f"section {k}: exhibit window {ex.window_days} days is out of range")
        errs += [
            f"section {k} challenge: {t}"
            for t in unsupported([c.answer for c in s.challenges], every)
        ]
    return errs
