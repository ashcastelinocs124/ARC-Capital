"""Trade Lab's checks. Numbers: the Morning Note's guard (every %, bp or pp figure must be a number of a
cited fact). Shape: the report's fixed structure. Style: no dashes as punctuation."""

from __future__ import annotations

import re

from castelino.agents.trade.models import BODY, Report
from castelino.agents.update.guard import _FIG, unsupported
from castelino.agents.update.models import Fact

DASHES = ("—", "–")
# fact ids a model writes into prose, "[NA1.14, NB1.43]" or "(F1.3)": they belong in fact_ids (the chips)
_IDS = re.compile(r"\s*[\[(](?:[A-Z]{1,3}\d+\.\d+(?:,\s*)?)+[\])]")


def strip_ids(text: str) -> str:
    return _IDS.sub("", text)


def figures(text: str) -> set[float]:
    """The %/bp/pp figures in a text (the user's Substack edits count as their own source)."""
    return {float(m.group(1) + m.group(2)) for m in _FIG.finditer(text)}


def cited_errors(
    texts: list[str], fact_ids: list[str], by: dict[str, Fact], extra: frozenset = frozenset()
) -> list[str]:
    errs = [f"unknown fact {i}" for i in fact_ids if i not in by]
    nums = {n for i in fact_ids if i in by for n in by[i].numbers} | extra
    return errs + unsupported(texts, nums)


def dash_errors(texts: list[str]) -> list[str]:
    return [f"dash in: {t[:80]}" for t in texts if any(d in t for d in DASHES)]


def report_errors(report: Report, by: dict[str, Fact], extra: frozenset = frozenset()) -> list[str]:
    errs: list[str] = []
    if len(report.introduction) != 2:
        errs.append(f"need 2 introduction paragraphs, got {len(report.introduction)}")
    if len(report.takeaways) != 3:
        errs.append(f"need 3 takeaways, got {len(report.takeaways)}")
    keys = [s.key for s in report.sections]
    if keys != list(BODY):
        errs.append(f"sections must be {list(BODY)}, got {keys}")
    every = {n for f in by.values() for n in f.numbers} | extra
    loose = [
        report.title,
        report.subtitle,
        *report.introduction,
        *report.takeaways,
        report.what_to_watch,
    ]
    errs += [f"intro/takeaways/watch: {t}" for t in unsupported(loose, every)]
    for s in report.sections:
        errs += [f"{s.key}: {e}" for e in cited_errors(s.paragraphs, s.fact_ids, by, extra)]
    errs += dash_errors(loose + [p for s in report.sections for p in [s.heading, *s.paragraphs]])
    return errs
