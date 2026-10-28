import pytest

from castelino.adoption.index import aggregate, headline
from castelino.adoption.models import Claim, Company, CompanyScore
from castelino.adoption.store import AdoptionStore
from castelino.dashboards.ai_capex import adoption

IT, HC = "Information Technology", "Health Care"
COS = [  # ticker, bucket, sector, max claim depth (None = no claim)
    ("AAA", "large", IT, 3), ("BBB", "large", IT, 2), ("CCC", "large", HC, None),
    ("SSS", "small", HC, 1), ("TTT", "small", IT, 3),
    ("MSFT", "large", IT, 3),  # a dashboard company: left out
]  # fmt: skip


def score(t, b, s):
    return CompanyScore(
        Company(t, b, s, 10.0), {}, {}, 50.0, 1, accession=f"acc-{t}"
    )  # fmt: skip


@pytest.fixture
def store(tmp_path):
    st = AdoptionStore(tmp_path / "adoption.db")
    scores = [score(t, b, s) for t, b, s, _ in COS]
    st.save_period("2026-10-12", scores, aggregate(scores))
    for t, _, _, depth in COS:
        claims = [
            Claim(quote=f"{t} uses AI at depth {d}.", depth=d) for d in range(1, (depth or 0) + 1)
        ]
        if t == "AAA":
            claims.append(Claim(quote="We deploy Microsoft 365 Copilot across the firm.", depth=2))
        st.put_filing(t, f"acc-{t}", 1000, 1.0, claims)
    return st


def test_slice_excludes_dashboard_companies(store):
    got = adoption.talk_slice(store, {"MSFT"}, names={"AAA": "Alpha Inc."})
    assert got["period"] == "2026-10-12"
    assert got["buckets"]["all"]["n"] == 5
    assert got["buckets"]["large"]["n"] == 3 and got["buckets"]["large"]["with_claim"] == 2
    assert got["buckets"]["large"]["pct"] == 67
    assert all("MSFT" not in q["quote"] for b in got["buckets"].values() for q in b["quotes"])
    assert got["product_claims"] == {"named": 1, "total": 10}  # AAA 4 + BBB 2 + SSS 1 + TTT 3


def test_depth_shares(store):
    b = adoption.talk_slice(store, {"MSFT"})["buckets"]["all"]
    assert b["with_claim"] == 4  # max depths 3, 2, 1, 3
    assert b["depth"] == [25, 25, 50]
    q = b["quotes"]
    assert len(q) == 2 and q[0]["quote"].endswith("depth 3.")
    it = next(s for s in b["sectors"] if s["sector"] == IT)
    assert (it["n"], it["pct"], it["thin"]) == (3, 100, True)


def test_empty_bucket(store):
    mid = adoption.talk_slice(store, {"MSFT"})["buckets"]["mid"]
    assert mid == {
        "n": 0,
        "with_claim": 0,
        "pct": None,
        "depth": [0, 0, 0],
        "sectors": [],
        "quotes": [],
    }


def test_no_period_is_none(tmp_path):
    assert adoption.talk_slice(AdoptionStore(tmp_path / "x.db"), set()) is None


def test_headline_and_series_carry_mid(store):
    h = headline(store.cells("2026-10-12"))
    assert "mid_ew" in h and h["mid_ew"] is None
    s = store.series()[0]
    assert (
        s["mid_ew"] is None and s["n"] == 6
    )  # n: companies in that period (a universe change shows)
