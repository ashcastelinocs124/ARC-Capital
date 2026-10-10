from datetime import date

import pandas as pd
import pytest

from castelino.cross_asset import consensus as c

ANSWER = (
    "September payrolls rose 142,000, above the 110K economists expected [1]. "
    "The report was released on 2026-10-02.\n"
    '{"release_date": "2026-10-02", "actual": 142, "consensus": 110}'
)
CITES = [("BLS", "https://bls.gov/x", 0, 75)]


def test_number_cited_accepts_formats():
    text = "rose 142,000 vs 110K expected; core CPI 0.3% vs +0.30 consensus"
    cites = [("s", "u", 0, len(text))]
    assert c.number_cited(text, cites, 142)  # thousands written out
    assert c.number_cited(text, cites, 110)
    assert c.number_cited(text, cites, 0.3)


def test_number_only_in_json_line_is_rejected():
    text = 'Payrolls beat expectations [1].\n{"release_date": "2026-10-02", "actual": 142, "consensus": 110}'
    assert not c.number_cited(text[: text.index("{")], [("s", "u", 0, 30)], 142)


def test_lookup_parses_and_verifies():
    rec = c.lookup("payrolls", "2026-09", search=lambda s, u: (ANSWER, CITES))
    assert rec == {
        "release_date": "2026-10-02",
        "actual": 142.0,
        "consensus": 110.0,
        "url": "https://bls.gov/x",
    }


def test_lookup_rejects_fabricated_consensus():
    bad = ANSWER.replace('"consensus": 110', '"consensus": 95')
    assert c.lookup("payrolls", "2026-09", search=lambda s, u: (bad, CITES)) is None


def test_attempts_count_only_after_release_is_surely_out():
    cache = {}

    def nothing(s, u):
        return "no data yet", []

    # payrolls for 2026-09 can come out from 2026-10-01; surely out by 2026-11-01
    c.update(cache, date(2026, 10, 2), search=nothing, start=date(2026, 9, 1))
    assert cache["payrolls:2026-09"]["attempts"] == 0
    for _ in range(3):
        c.update(cache, date(2026, 11, 5), search=nothing, start=date(2026, 9, 1))
    assert cache["payrolls:2026-09"]["status"] == "not_found"
    calls = []
    c.update(
        cache,
        date(2026, 11, 6),
        search=lambda s, u: calls.append(u) or ("", []),
        start=date(2026, 9, 1),
    )
    assert cache["payrolls:2026-09"]["attempts"] == 3
    assert not any("Nonfarm payrolls" in u and "2026-09" in u for u in calls)  # final


def test_cap_limits_searches():
    calls = []
    c.update(
        {},
        date(2026, 10, 9),
        search=lambda s, u: calls.append(1) or ("", []),
        cap=2,
        start=date(2025, 1, 1),
    )
    assert len(calls) == 2


def test_weekly_surprises_z_and_groups():
    cache = {}
    vals = [(0.3, 0.3), (0.4, 0.3), (0.2, 0.3), (0.3, 0.3), (0.5, 0.3)]
    days = ["2026-05-13", "2026-06-10", "2026-07-15", "2026-08-12", "2026-09-11"]
    for i, ((a, k), d) in enumerate(zip(vals, days, strict=True)):
        cache[f"core_cpi:2026-0{4 + i}"] = {
            "status": "ok",
            "release_date": d,
            "actual": a,
            "consensus": k,
            "url": "u",
            "attempts": 1,
        }
    weeks = pd.date_range("2026-05-01", "2026-09-25", freq="W-FRI")
    df, rows, gaps = c.weekly_surprises(cache, weeks)
    sd = pd.Series([a - k for a, k in vals]).std(ddof=0)
    assert df.loc[pd.Timestamp("2026-09-11"), "inflation"] == pytest.approx(0.2 / sd)
    assert df.loc[pd.Timestamp("2026-05-22"), "inflation"] == 0  # no release that week
    assert (df["growth"] == 0).all()
    assert rows[-1]["z"] == pytest.approx(0.2 / sd, abs=0.01) and rows[-1]["group"] == "inflation"
