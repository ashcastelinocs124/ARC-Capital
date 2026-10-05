"""One bi-weekly run: sources -> extract -> guard -> pillars -> scores -> index -> store."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from castelino.adoption.index import aggregate
from castelino.adoption.models import PILLARS, Claim, Company, CompanyScore
from castelino.adoption.score import company_score, hire_raw, pillar_scores, spend_raw, talk_raw
from castelino.adoption.sources.edgar import Filing
from castelino.adoption.sources.jobs import JobCounts
from castelino.adoption.store import AdoptionStore

log = logging.getLogger(__name__)


@dataclass
class Deps:
    companies: list[Company]
    filing_for: Callable[[str], Filing | None]
    text_for: Callable[[Filing], str]
    extract: Callable[[str, str], tuple[list[Claim], list[Claim]]]
    jobs_for: Callable[[str], JobCounts | None]
    financials_for: Callable[[str], tuple[float | None, float | None, float | None]]
    store: AdoptionStore
    smoothing_periods: int = 7
    thin_below: int = 5


@dataclass
class RunSummary:
    period: str
    n_companies: int
    n_scored: int
    n_excluded: int
    n_errors: int
    errors: list[str] = field(default_factory=list)


def run_period(period: str, deps: Deps) -> RunSummary:
    raw: dict[str, dict[str, float | None]] = {}
    snapshots: dict[str, float | None] = {}
    accessions: dict[str, str | None] = {}
    errors: list[str] = []

    for co in deps.companies:
        t = co.ticker
        raw[t] = {k: None for k in PILLARS}
        snapshots[t], accessions[t] = None, None

        try:  # Talk: carried forward from the cache until the company files again
            filing = deps.filing_for(t)
            if filing is not None:
                accessions[t] = filing.accession
                cached = deps.store.get_filing(t, filing.accession)
                if cached is not None:
                    raw[t]["talk"] = cached["talk_raw"]
                else:
                    text = deps.text_for(filing)  # download only on a cache miss
                    kept, dropped = deps.extract(t, text)
                    if dropped:
                        log.info("%s: guard dropped %d claim(s)", t, len(dropped))
                    words = len(text.split())
                    talk = talk_raw([c.depth for c in kept], words)
                    deps.store.put_filing(t, filing.accession, words, talk, kept)
                    raw[t]["talk"] = talk
        except Exception as e:  # noqa: BLE001 - one failing source costs one pillar
            errors.append(f"{t} talk: {e}")

        try:  # Hire: mean of the last snapshots (the boards only show currently open roles)
            counts = deps.jobs_for(t)
            if counts is not None:
                snap = hire_raw(counts.ai, counts.total)
                snapshots[t] = snap
                if snap is not None:
                    hist = deps.store.hire_history(t, period, deps.smoothing_periods - 1)
                    raw[t]["hire"] = sum(hist + [snap]) / (len(hist) + 1)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{t} hire: {e}")

        try:
            capex, rnd, revenue = deps.financials_for(t)
            raw[t]["spend"] = spend_raw(capex, rnd, revenue)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{t} spend: {e}")

    pillar = pillar_scores(raw)
    rows: list[CompanyScore] = []
    for co in deps.companies:
        score, used = company_score(pillar[co.ticker])
        rows.append(
            CompanyScore(
                co,
                raw[co.ticker],
                pillar[co.ticker],
                score,
                used,
                hire_snapshot=snapshots[co.ticker],
                accession=accessions[co.ticker],
            )
        )

    deps.store.save_period(period, rows, aggregate(rows, deps.thin_below))
    scored = sum(r.score is not None for r in rows)
    return RunSummary(period, len(rows), scored, len(rows) - scored, len(errors), errors)
