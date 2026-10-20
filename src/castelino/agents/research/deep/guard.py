"""The report's checks: every %/bp/pp figure in a point must be a number of a fact it cites (Trade Lab's
number guard), a figure only an X post backs must name that post's @handle in the same sentence, every point
needs a real owner, and no dashes as punctuation. The latest-data check: every point needs a figure from
fresh_year(); the writer gets one retry, then dated() keeps an older point but says so and marks it."""

from __future__ import annotations

import re
from datetime import date

from castelino.agents.research.deep.models import Point, ReportDraft
from castelino.agents.research.deep.tools import handle, is_x
from castelino.agents.trade.guard import cited_errors, dash_errors
from castelino.agents.update.guard import unsupported
from castelino.agents.update.models import Fact

_SENT = re.compile(r"(?<=[.!?])\s+")
_YEAR = re.compile(r"(?<![\d,.])(20\d\d)(?![\d,])")  # a year, not "2,025" or "12025"
# fact ids written into prose, "[A3, B12]" or "(G2)": they belong in fact_ids (the chips)
_IDS = re.compile(r"\s*[\[(](?:[A-P]\d+(?:,\s*)?)+[\])]")


def strip_ids(text: str) -> str:
    return _IDS.sub("", text)


def x_attribution_errors(texts: list[str], fact_ids: list[str], by: dict[str, Fact]) -> list[str]:
    """ponytail: any cited X handle in the sentence counts, not only the one whose post holds the figure."""
    xs = [by[i] for i in fact_ids if i in by and is_x(by[i])]
    if not xs:
        return []
    other = {n for i in fact_ids if i in by and not is_x(by[i]) for n in by[i].numbers}
    from_x = {n for f in xs for n in f.numbers}
    handles = {"@" + handle(f).lower() for f in xs}
    errs: list[str] = []
    for text in texts:
        for s in _SENT.split(text):
            only_x = set(unsupported([s], other)) - set(unsupported([s], from_x))
            if only_x and not any(h in s.lower() for h in handles):
                errs += [
                    f"{t} comes from an X post: name its @handle in the same sentence"
                    for t in sorted(only_x)
                ]
    return errs


def point_errors(p, by: dict[str, Fact]) -> list[str]:
    texts = [p.headline, p.body]
    return (
        cited_errors(texts, p.fact_ids, by)
        + x_attribution_errors(texts, p.fact_ids, by)
        + dash_errors(texts)
    )


def report_errors(draft: ReportDraft, by: dict[str, Fact], owners: set[str]) -> list[str]:
    errs = [] if draft.points else ["the report has no points"]
    for k, p in enumerate(draft.points, 1):
        if p.agent not in owners:
            errs.append(f"point {k}: agent {p.agent!r} is not one of {sorted(owners)}")
        errs += [f"point {k}: {e}" for e in point_errors(p, by)]
    loose = [draft.title, draft.subtitle, *draft.caveats]
    every = {n for f in by.values() for n in f.numbers}
    errs += [f"title/caveats: {t}" for t in unsupported(loose, every)]
    return errs + dash_errors(loose)


def fresh_year(today: date) -> int:
    """The oldest year that counts as the latest data: this year, or last year until the end of March."""
    return today.year if today.month > 3 else today.year - 1


def newest_year(fact_ids: list[str], by: dict[str, Fact], today: date) -> int:
    """The newest year the cited facts name (an X post is from the last 7 days); 0 when none names one."""
    years = [
        today.year if is_x(by[i]) else max(map(int, _YEAR.findall(by[i].text)), default=0)
        for i in fact_ids
        if i in by
    ]
    return max(years, default=0)


def stale_errors(points, by: dict[str, Fact], today: date) -> list[str]:
    fresh, errs = fresh_year(today), []
    for k, p in enumerate(points, 1):
        y = newest_year(p.fact_ids, by, today)
        if y < fresh and "latest available" not in p.body.lower():
            errs.append(
                f"point {k}: its newest figure is from {y or 'an undated source'}; back it with a {fresh} "
                "figure from that researcher's facts, or say in the body that it is the latest available"
            )
    return errs


def dated(p: Point, by: dict[str, Fact], today: date) -> Point:
    """A point whose newest figure is older than fresh_year keeps it, says so once and gets `older`."""
    y = newest_year(p.fact_ids, by, today)
    if y >= fresh_year(today):
        return p.model_copy(update={"older": ""})
    if "latest available" in p.body.lower():
        note = ""
    elif y:
        note = f" These are the latest figures available, from {y}."
    else:
        note = " The sources give no date for these figures."
    return p.model_copy(update={"older": str(y) if y else "undated", "body": p.body + note})
