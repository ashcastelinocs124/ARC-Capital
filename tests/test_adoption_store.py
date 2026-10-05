import pytest

from castelino.adoption.index import aggregate
from castelino.adoption.models import Claim, Company, CompanyScore
from castelino.adoption.store import AdoptionStore


def make_scores(a_snapshot=0.1):
    a = Company("A", "large", "Information Technology", 300.0)
    b = Company("B", "small", "Health Care", 8.0)
    return [
        CompanyScore(a, {"talk": 2.0, "hire": a_snapshot, "spend": 0.3},
                     {"talk": 70.0, "hire": 60.0, "spend": 80.0}, 70.0, 3,
                     hire_snapshot=a_snapshot, accession="acc-A"),
        CompanyScore(b, {"talk": None, "hire": None, "spend": None},
                     {"talk": None, "hire": None, "spend": None}, None, 0),
    ]


@pytest.fixture
def store(tmp_path):
    return AdoptionStore(tmp_path / "adoption.db")


def test_roundtrip_and_ordering(store):
    scores = make_scores()
    cells = aggregate(scores)
    store.save_period("2026-10-01", scores, cells)
    assert store.periods() == ["2026-10-01"]
    assert store.cells("2026-10-01") == cells
    rows = store.companies("2026-10-01")
    assert [r["ticker"] for r in rows] == ["A", "B"]          # unscored last
    assert rows[0]["score"] == 70.0 and rows[0]["accession"] == "acc-A" and rows[1]["score"] is None
    only_b = store.companies("2026-10-01", sector="Health Care", bucket="small")
    assert [r["ticker"] for r in only_b] == ["B"]


def test_save_period_is_idempotent(store):
    scores = make_scores()
    for _ in range(2):
        store.save_period("2026-10-01", scores, aggregate(scores))
    assert len(store.companies("2026-10-01")) == 2
    assert len(store.cells("2026-10-01")) == len(aggregate(scores))


def test_hire_history_excludes_current_and_later(store):
    for period, snap in [("2026-10-01", 0.1), ("2026-10-15", 0.3)]:
        sc = make_scores(snap)
        store.save_period(period, sc, aggregate(sc))
    assert sorted(store.hire_history("A", "2026-10-29", 5)) == [0.1, 0.3]
    assert store.hire_history("A", "2026-10-15", 5) == [0.1]
    assert store.hire_history("B", "2026-10-29", 5) == []


def test_filing_cache_and_claims(store):
    assert store.get_filing("A", "acc-A") is None
    store.put_filing("A", "acc-A", 1000, 2.5, [Claim(quote="q", depth=2)])
    assert store.get_filing("A", "acc-A") == {"words": 1000, "talk_raw": 2.5}
    store.put_filing("A", "acc-A", 1000, 2.5, [Claim(quote="q", depth=2)])   # replaces, not duplicates
    assert store.claims_for("A", "acc-A") == [{"depth": 2, "quote": "q"}]


def test_series_has_none_for_missing_bucket(store):
    sc = make_scores()
    store.save_period("2026-10-01", sc, aggregate(sc))
    assert store.series() == [{"period": "2026-10-01", "large_ew": 70.0, "small_ew": None}]
