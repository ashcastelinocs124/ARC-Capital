"""Number guard for the Morning Note.

Every %, bp or pp figure the Editor writes must be one of the numbers code attached to the facts
behind the findings it cites (item text → that item's findings; headline and takeaways → any
finding). Facts come from fetched data or from a cited line of a web-search answer, so the
Editor cannot add a number no source gave.
"""

from __future__ import annotations

import re

from castelino.agents.update.models import Fact, Finding, MorningNote

# ponytail: only figures carrying a unit are checked; plain counts like "day 10" or years pass.
_UNIT = r"(%|percent|per cent|pct|percentage[\s-]points?|ppts?|pp|basis[\s-]points?|bps|bp)"
_FIG = re.compile(r"(?<![\w.])([-+]?)(\d+(?:\.\d+)?)[\s-]*" + _UNIT + r"(?![a-z])", re.I)


def _supported(value: float, decimals: int, signed: bool, nums: set[float]) -> bool:
    tol = 0.5 * 10**-decimals + 1e-9  # half a unit of the displayed precision
    if signed:
        return any(abs(n - value) <= tol for n in nums)
    return any(abs(abs(n) - abs(value)) <= tol for n in nums)


def unsupported(texts: list[str], nums: set[float]) -> list[str]:
    bad: list[str] = []
    for text in texts:
        for m in _FIG.finditer(text):
            sign, digits = m.group(1), m.group(2)
            decimals = len(digits.split(".")[1]) if "." in digits else 0
            if not _supported(float(sign + digits), decimals, bool(sign), nums):
                tok = m.group(0).strip()
                if tok not in bad:
                    bad.append(tok)
    return bad


def check_note(
    note: MorningNote, findings: list[Finding], facts: list[Fact], *, max_items: int = 5
) -> list[str]:
    fact_by = {f.id: f for f in facts}
    find_by = {f.id: f for f in findings}

    def nums_for(fids: list[str]) -> set[float]:
        out: set[float] = set()
        for fid in fids:
            for fact_id in find_by[fid].fact_ids if fid in find_by else []:
                if fact_id in fact_by:
                    out.update(fact_by[fact_id].numbers)
        return out

    errs: list[str] = []
    if len(note.takeaways) != 3:
        errs.append("need exactly 3 takeaways")
    if not 3 <= len(note.items) <= max_items:
        errs.append(f"need 3-{max_items} items")
    ranks = [it.rank for it in note.items]
    errs += [f"duplicate rank {r}" for r in sorted({r for r in ranks if ranks.count(r) > 1})]
    charts = [it.chart for it in note.items if it.chart]
    errs += [
        f"finding {c} charted twice" for c in sorted({c for c in charts if charts.count(c) > 1})
    ]
    for it in note.items:
        errs += [
            f"item {it.rank}: unknown finding {fid}" for fid in it.finding_ids if fid not in find_by
        ]
        if it.chart is not None and it.chart not in it.finding_ids:
            errs.append(f"item {it.rank}: chart {it.chart} is not one of its findings")
        nums = nums_for(it.finding_ids)
        errs += [f"item {it.rank}: {t}" for t in unsupported([it.title, it.body], nums)]
    every = nums_for(list(find_by))
    errs += [
        f"headline/takeaways: {t}" for t in unsupported([note.headline, *note.takeaways], every)
    ]
    return errs
