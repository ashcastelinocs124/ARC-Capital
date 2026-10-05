import pytest

from castelino.adoption.index import Cell, aggregate, headline
from castelino.adoption.models import Company, CompanyScore


def cs(ticker, bucket, sector, cap, score):
    return CompanyScore(Company(ticker, bucket, sector, cap), {}, {}, score, 3 if score is not None else 0)


def test_aggregate_equal_and_cap_weighted():
    scores = [
        cs("A", "large", "Information Technology", 1.0, 60.0),
        cs("B", "large", "Information Technology", 1.0, 70.0),
        cs("C", "large", "Information Technology", 2.0, 80.0),
        cs("D", "small", "Financials", 5.0, 40.0),
    ]
    cells = aggregate(scores)
    large_it = next(c for c in cells if c.sector == "Information Technology" and c.bucket == "large")
    assert large_it.n == 3 and large_it.thin is True
    assert large_it.ew == pytest.approx(70.0)
    assert large_it.cw == pytest.approx((60 + 70 + 160) / 4)
    bucket = next(c for c in cells if c.sector is None and c.bucket == "large")
    assert bucket.n == 3
    assert [(c.bucket, c.sector) for c in cells] == [
        ("large", None), ("large", "Information Technology"), ("small", None), ("small", "Financials"),
    ]


def test_aggregate_excludes_unscored_and_flags_thin():
    scores = [cs(f"T{i}", "large", "Energy", 1.0, 50.0) for i in range(5)] + [cs("X", "large", "Energy", 1.0, None)]
    energy = next(c for c in aggregate(scores) if c.sector == "Energy")
    assert energy.n == 5 and energy.thin is False   # N < 5 is thin; exactly 5 is not


def test_headline_spread_and_concentration():
    cells = [
        Cell(None, "large", 3, 70.0, 72.5, True),
        Cell(None, "small", 1, 40.0, 40.0, True),
    ]
    h = headline(cells)
    assert h["spread"] == pytest.approx(-30.0)
    assert h["large_concentration"] == pytest.approx(2.5)
    assert h["small_concentration"] == pytest.approx(0.0)


def test_aggregate_missing_bucket_has_no_spread():
    cells = aggregate([cs("A", "large", "Energy", 1.0, 55.0)])
    h = headline(cells)
    assert h["small_ew"] is None and h["spread"] is None
