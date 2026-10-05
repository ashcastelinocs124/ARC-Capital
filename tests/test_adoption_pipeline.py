import pytest

from castelino.adoption.models import Claim, Company
from castelino.adoption.pipeline import Deps, run_period
from castelino.adoption.sources.edgar import Filing
from castelino.adoption.sources.jobs import JobCounts
from castelino.adoption.store import AdoptionStore

COMPANIES = [
    Company("A", "large", "Information Technology", 300.0),
    Company("B", "large", "Information Technology", 200.0),
    Company("C", "large", "Financials", 100.0),
    Company("D", "small", "Information Technology", 10.0),
    Company("E", "small", "Health Care", 8.0),
    Company("F", "small", "Health Care", 6.0),
]
DEPTHS = {"A": [3, 3], "B": [2], "C": [1], "D": [2], "E": [1]}  # F has no filing
JOBS = {"A": (10, 100), "B": (5, 100), "C": (1, 100), "D": (3, 30)}  # E, F have no board
FIN = {"A": (10.0, 20.0, 100.0), "B": (5.0, 5.0, 100.0), "D": (1.0, 1.0, 50.0)}


def make_deps(store, jobs=None, calls=None, fetched=None) -> Deps:
    jobs = jobs or JOBS

    def filing_for(t):
        if t not in DEPTHS:
            return None
        return Filing(t, f"acc-{t}", "10-K", f"https://sec.example/{t}.htm")

    def text_for(filing):
        if fetched is not None:
            fetched.append(filing.ticker)
        return " ".join(["word"] * 1000)

    def extract(t, text):
        if calls is not None:
            calls.append(t)
        return [Claim(quote="q", depth=d) for d in DEPTHS[t]], []

    return Deps(
        companies=COMPANIES,
        filing_for=filing_for,
        text_for=text_for,
        extract=extract,
        jobs_for=lambda t: JobCounts(*jobs[t]) if t in jobs else None,
        financials_for=lambda t: FIN.get(t, (None, None, None)),
        store=store,
    )


@pytest.fixture
def store(tmp_path):
    return AdoptionStore(tmp_path / "adoption.db")


def row(store, period, ticker):
    return next(r for r in store.companies(period) if r["ticker"] == ticker)


def test_run_period_scores_and_excludes(store):
    s = run_period("2026-10-01", make_deps(store))
    assert (s.n_companies, s.n_scored, s.n_excluded, s.n_errors) == (6, 4, 2, 0)
    assert row(store, "2026-10-01", "A")["score"] > row(store, "2026-10-01", "B")["score"]
    assert row(store, "2026-10-01", "E")["score"] is None  # talk only: 1 pillar
    assert row(store, "2026-10-01", "F")["score"] is None  # nothing at all
    assert row(store, "2026-10-01", "C")["pillars_used"] == 2  # talk + hire, no spend
    cells = store.cells("2026-10-01")
    assert next(c for c in cells if c.sector is None and c.bucket == "large").n == 3
    assert next(c for c in cells if c.sector is None and c.bucket == "small").n == 1
    assert store.claims_for("A", "acc-A")[0]["depth"] == 3


def test_run_period_is_idempotent(store):
    deps = make_deps(store)
    run_period("2026-10-01", deps)
    run_period("2026-10-01", deps)
    assert len(store.companies("2026-10-01")) == 6
    assert len(store.cells("2026-10-01")) == len(
        set((c.sector, c.bucket) for c in store.cells("2026-10-01"))
    )


def test_filing_is_not_re_extracted_and_hire_is_smoothed(store):
    calls: list[str] = []
    run_period("2026-10-01", make_deps(store, calls=calls))
    assert len(calls) == 5
    run_period("2026-10-15", make_deps(store, jobs={**JOBS, "A": (20, 100)}, calls=calls))
    assert len(calls) == 5  # same accessions: Talk carried forward
    a = row(store, "2026-10-15", "A")
    assert a["hire_snapshot"] == pytest.approx(0.2)
    assert a["hire_raw"] == pytest.approx(0.15)  # mean of 0.1 and 0.2


def test_one_failing_source_costs_one_pillar_not_the_run(store):
    deps = make_deps(store)
    good = deps.filing_for

    def flaky(t):
        if t == "B":
            raise RuntimeError("edgar down")
        return good(t)

    deps.filing_for = flaky
    s = run_period("2026-10-01", deps)
    assert s.n_errors == 1 and "B" in s.errors[0]
    b = row(store, "2026-10-01", "B")
    assert b["talk_raw"] is None and b["score"] is not None  # hire + spend still score it


def test_filing_without_ai_claims_is_zero_not_missing(store):
    deps = make_deps(store)
    deps.extract = lambda t, text: ([], [])
    run_period("2026-10-01", deps)
    assert row(store, "2026-10-01", "A")["talk_raw"] == 0.0


def test_cached_filing_is_not_downloaded_again(store):
    fetched: list[str] = []
    run_period("2026-10-01", make_deps(store, fetched=fetched))
    assert len(fetched) == 5
    run_period("2026-10-15", make_deps(store, fetched=fetched))
    assert len(fetched) == 5  # same accessions: no second download
