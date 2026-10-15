"""Trade Lab's checks. Numbers: the Morning Note's guard (every %, bp or pp figure must be a number of a
cited fact). Shape: the report's fixed structure. Style: no dashes as punctuation."""

from __future__ import annotations

from castelino.agents.trade.models import BODY, Report
from castelino.agents.update.guard import unsupported
from castelino.agents.update.models import Fact

DASHES = ("—", "–")


def cited_errors(texts: list[str], fact_ids: list[str], by: dict[str, Fact]) -> list[str]:
    errs = [f"unknown fact {i}" for i in fact_ids if i not in by]
    nums = {n for i in fact_ids if i in by for n in by[i].numbers}
    return errs + unsupported(texts, nums)


def dash_errors(texts: list[str]) -> list[str]:
    return [f"dash in: {t[:80]}" for t in texts if any(d in t for d in DASHES)]


def report_errors(report: Report, by: dict[str, Fact]) -> list[str]:
    errs: list[str] = []
    if len(report.introduction) != 2:
        errs.append(f"need 2 introduction paragraphs, got {len(report.introduction)}")
    if len(report.takeaways) != 3:
        errs.append(f"need 3 takeaways, got {len(report.takeaways)}")
    keys = [s.key for s in report.sections]
    if keys != list(BODY):
        errs.append(f"sections must be {list(BODY)}, got {keys}")
    every = {n for f in by.values() for n in f.numbers}
    loose = [
        report.title,
        report.subtitle,
        *report.introduction,
        *report.takeaways,
        report.what_to_watch,
    ]
    errs += [f"intro/takeaways/watch: {t}" for t in unsupported(loose, every)]
    for s in report.sections:
        errs += [f"{s.key}: {e}" for e in cited_errors(s.paragraphs, s.fact_ids, by)]
    errs += dash_errors(loose + [p for s in report.sections for p in [s.heading, *s.paragraphs]])
    return errs
