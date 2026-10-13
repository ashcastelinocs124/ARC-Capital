"""Number guard for the Morning Note.

Every %, bp or pp figure the Editor writes must be one of the numbers code attached to the facts
behind the findings it cites (item text → that item's findings; headline and takeaways → any
finding). Facts come from fetched data or from a cited line of a web-search answer, so the
Editor cannot add a number no source gave.
"""

from __future__ import annotations

import logging
import re

from castelino.agents.update.models import Fact, Finding, MorningNote, NoteItem

log = logging.getLogger(__name__)

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


def count_figures(texts: list[str]) -> int:
    """How many unit-carrying figures the guard checked (shown on the report's page 1)."""
    return sum(1 for t in texts for _ in _FIG.finditer(t))


def check_note(
    note: MorningNote, findings: list[Finding], facts: list[Fact], *, items: int = 5
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
    if len(note.items) != items:
        errs.append(f"need exactly {items} items")
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
    if any(f.agent == "ai" for f in findings) and not any(
        find_by[fid].agent == "ai" for it in note.items for fid in it.finding_ids if fid in find_by
    ):
        errs.append("no item cites an (ai) finding; include one AI & chips item")
    every = nums_for(list(find_by))
    errs += [
        f"headline/takeaways: {t}" for t in unsupported([note.headline, *note.takeaways], every)
    ]
    return errs


# ── chart picks ────────────────────────────────────────────────────────────
POINTS = {
    "movers": (2, 8),
    "ladder": (2, 6),
    "dumbbell": (2, 2),
    "range": (3, 3),
    "vs_expected": (2, 2),
}


def _series(f: Fact | None, kind: str) -> bool:
    if f is None or f.series is None or f.series.kind != kind:
        return False
    if kind == "release":
        return len(f.series.points) >= 3
    return f.series.provider in ("fred", "yahoo")


def pick_errors(it: NoteItem, findings: list[Finding], facts: list[Fact]) -> list[str]:
    """Why an item's chart pick can't be drawn truthfully ([] = fine). Not fatal: the runner
    drops a bad pick and the item keeps its line chart."""
    ex = it.exhibit
    if ex is None:
        return []
    fact_by = {f.id: f for f in facts}
    find_by = {f.id: f for f in findings}
    own = {i for fid in it.finding_ids if fid in find_by for i in find_by[fid].fact_ids}
    ids = ex.fact_ids + [p.fact_id for p in ex.points]
    errs = [f"{i} is not one of the item's facts" for i in dict.fromkeys(ids) if i not in own]
    if ex.kind in ("line", "compare") and not 5 <= ex.window_days <= 3650:
        errs.append(f"window {ex.window_days} days is out of range")
    if ex.kind == "line" and not (
        len(ex.fact_ids) == 1 and _series(fact_by.get(ex.fact_ids[0]), "daily")
    ):
        errs.append("line needs one fact with a daily series")
    elif ex.kind == "compare" and not (
        2 <= len(ex.fact_ids) <= 4 and all(_series(fact_by.get(i), "daily") for i in ex.fact_ids)
    ):
        errs.append("compare needs 2-4 facts with a daily series")
    elif ex.kind == "columns" and not (
        len(ex.fact_ids) == 1 and _series(fact_by.get(ex.fact_ids[0]), "release")
    ):
        errs.append("columns needs one fact with a release history")
    elif ex.kind in POINTS:
        lo, hi = POINTS[ex.kind]
        if not lo <= len(ex.points) <= hi:
            errs.append(f"{ex.kind} needs {lo}-{hi} points")
        elif (
            ex.kind == "range"
            and not ex.points[0].value <= ex.points[1].value <= ex.points[2].value
        ):
            errs.append("range points must be [low, last, high]")
    for p in ex.points:
        nums = set(fact_by[p.fact_id].numbers) if p.fact_id in fact_by else set()
        txt = f"{p.value:g}"
        decimals = len(txt.split(".")[1]) if "." in txt else 0
        if not _supported(p.value, decimals, True, nums):
            errs.append(f"point {p.label}={txt} is not a number of {p.fact_id}")
    nums = {n for i in own if i in fact_by for n in fact_by[i].numbers}
    errs += [f"title: {t}" for t in unsupported([ex.title], nums)]
    return errs


def clean_picks(note: MorningNote, findings: list[Finding], facts: list[Fact]) -> MorningNote:
    items = []
    for it in note.items:
        if errs := pick_errors(it, findings, facts):
            log.warning("item %s chart pick dropped: %s", it.rank, "; ".join(errs))
            it = it.model_copy(update={"exhibit": None})
        items.append(it)
    return note.model_copy(update={"items": items})
