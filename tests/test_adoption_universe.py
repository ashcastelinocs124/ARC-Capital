import pytest

from castelino.adoption.models import Company
from castelino.adoption.universe import build_universe, load_seed, load_universe, save_universe

INFO = {
    "A": {"marketCap": 300, "sector": "Technology"},
    "B": {"marketCap": 200, "sector": "Healthcare"},
    "C": {"marketCap": 100, "sector": "Financial Services"},
    "D": {"marketCap": 10, "sector": "Technology"},
    "E": {"marketCap": 8, "sector": "Weird Sector"},  # unmappable -> skipped
    "F": {"marketCap": None, "sector": "Energy"},  # no market cap -> skipped
}


def info_fn(t):
    if t == "G":
        raise RuntimeError("lookup failed")
    return INFO[t]


def test_build_universe_ranks_top_n_per_bucket_and_skips_bad_rows():
    seed = [
        ("A", "large"),
        ("B", "large"),
        ("C", "large"),
        ("D", "small"),
        ("E", "small"),
        ("F", "small"),
        ("G", "small"),
    ]
    out = build_universe(seed, info_fn, top_n=2)
    assert out == [
        Company("A", "large", "Information Technology", 300.0),
        Company("B", "large", "Health Care", 200.0),
        Company("D", "small", "Information Technology", 10.0),
    ]


def test_load_seed_validates_bucket(tmp_path):
    p = tmp_path / "seed.csv"
    p.write_text("ticker,bucket\naapl,large\nxyz,micro\n")
    with pytest.raises(ValueError, match="micro"):
        load_seed(p)
    p.write_text("ticker,bucket\naapl,large\n")
    assert load_seed(p) == [("AAPL", "large")]


def test_save_and_load_roundtrip(tmp_path):
    cos = [Company("A", "large", "Energy", 12.5), Company("B", "small", "Materials", 3.0)]
    p = tmp_path / "universe.csv"
    save_universe(p, cos)
    assert load_universe(p) == cos


def test_build_universe_drops_duplicate_tickers():
    seed = [("A", "large"), ("A", "large"), ("A", "small"), ("B", "large")]
    out = build_universe(seed, info_fn, top_n=10)
    assert [c.ticker for c in out] == ["A", "B"]
    assert out[0].bucket == "large"
