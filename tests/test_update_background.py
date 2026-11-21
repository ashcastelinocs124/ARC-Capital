import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from castelino.agents.update import background as bg
from castelino.agents.update.models import Fact, Finding, Point, SeriesRef

DAY = "2026-10-13"
UNIVERSE = [
    ("JPM", "JPMorgan Chase & Co."),
    ("NVDA", "NVIDIA Corporation"),
    ("GM", "General Motors"),
]


def fact(fid, text, series=None):
    return Fact(
        id=fid,
        text=text,
        numbers=[],
        provenance="reported",
        series=series,
        source_title="s",
        source_url="u",
    )


def finding(fid, claim, fact_ids, agent="news", series=None):
    return Finding(
        id=fid, agent=agent, claim=claim, provenance="reported", series=series,
        source_title="s", source_url="u", fact_ids=fact_ids,
    )  # fmt: skip


def closes(n=300, start=100.0, step=0.5, end=DAY):
    idx = pd.bdate_range(end=end, periods=n)
    return pd.Series(start + step * np.arange(n), index=idx, dtype=float)


def test_finds_named_tickers_universe_names_and_skips_acronyms():
    facts = [
        fact("I1", "Cerebras (CBRS) closed up; CPI (CPI) data due; Nvidia rose"),
        fact("N1", "JPMorgan’s earnings missed; General guidance was cut"),
    ]
    finds = [finding("ai-1", "Cerebras rose", ["I1"], "ai"), finding("news-1", "Banks", ["N1"])]
    got = bg.stock_subjects(finds, facts, UNIVERSE)
    assert got["CBRS"] == ("Cerebras", ["ai-1"])
    assert got["NVDA"][1] == ["ai-1"]  # all-caps NVIDIA matches "Nvidia"
    assert got["JPM"] == ("JPMorgan Chase", ["news-1"])
    assert "CPI" not in got and "GM" not in got  # "General" alone never names a company
    assert list(got)[0] == "CBRS"  # a named ticker outranks a name match


def test_people_and_places_are_not_companies():
    universe = [("BSX", "Boston Scientific Corporation"), ("WMB", "Williams Companies, Inc."),
                ("USB", "U.S. Bancorp")]  # fmt: skip
    facts = [
        fact("N1", "Boston Fed President Collins and New York Fed's Williams spoke on U.S. rates")
    ]
    assert bg.stock_subjects([finding("news-1", "Fed", ["N1"])], facts, universe) == {}


def test_stock_fact_horizons_and_range():
    s = closes()
    f = bg.stock_fact("bg-s1", "CBRS", "Cerebras", s, date.fromisoformat(DAY))
    last = s.iloc[-1]
    m1 = round((last / s.iloc[-22] - 1) * 100, 2)
    assert f"1 month {m1:+.2f}%" in f.text and m1 in f.numbers
    assert "52-week high" in f.text and "0.00% below the high" in f.text  # rising series
    assert f.series.provider == "yahoo" and f.series.id == "CBRS"


def test_stock_fact_names_a_fund_by_what_it_holds():
    f = bg.stock_fact("bg-s1", "XLK", "XLK", closes(), date.fromisoformat(DAY))
    assert f.text.startswith("Background, Tech stocks price history") and "XLK" not in f.text
    assert f.series.id == "XLK" and f.series.label == "Tech stocks"
    assert f.source_title == "Yahoo Finance"  # chart footers print it


def test_stock_fact_ignores_closes_after_the_day():
    s = closes(end="2026-10-20")
    f = bg.stock_fact("bg-s1", "X", "X", s, date.fromisoformat(DAY))
    assert "(Oct 13, 2026)" in f.text


def test_release_fact_streak_and_cut_at_reported_month():
    idx = pd.date_range("2024-01-01", "2026-10-01", freq="MS")
    vals = 100 * np.cumprod(1 + np.linspace(0.001, 0.01, len(idx)))  # m/m speeds up each month
    vals[-1] = vals[-2]  # Oct 2026 flat: must be cut, the note reports Sep 2026
    raw = pd.Series(vals, index=idx)
    ref = SeriesRef(
        kind="release", provider="fred", id="CPIAUCSL", label="CPI m/m",
        points=[Point(label="Aug 2026 data", value=0.9), Point(label="Sep 2026 data", value=0.9)],
    )  # fmt: skip
    f = bg.release_fact("bg-d1", ref, raw, date.fromisoformat(DAY))
    assert "Sep 2026" in f.text and "Oct 2026" not in f.text
    assert len(f.series.points) == 12 and f.series.kind == "release"
    assert "straight rise" in f.text and "the highest on record" in f.text


def test_streak():
    assert bg._streak([1, 2, 3, 4]) == (3, "rise")
    assert bg._streak([5, 4, 4]) == (0, "")
    assert bg._streak([3, 1, 2]) == (1, "rise")


def write_note(updates, day, title, body, findings=()):
    rec = {"version": 2, "date": day, "findings": list(findings),
           "note": {"items": [{"rank": 1, "title": title, "body": body, "finding_ids": []}]}}  # fmt: skip
    (updates / f"{day}.json").write_text(json.dumps(rec))


def test_enrich_links_background_and_is_idempotent(tmp_path):
    write_note(
        tmp_path,
        "2026-10-08",
        "Cerebras lockup looms",
        "**Cerebras** fell 3.5% as a lockup neared. More.",
    )
    write_note(tmp_path, "2026-09-01", "Too old", "Cerebras rose 9%.")  # outside the 30 days
    facts = [fact("I1", "Cerebras (CBRS) closed at $149.08")]
    finds = [finding("ai-1", "Cerebras rose", ["I1"], "ai")]
    kw = dict(
        fetch_close=lambda t: closes(), fetch_fred=lambda s: pd.Series(dtype=float), universe=[]
    )
    f2, facts2, gaps = bg.enrich(finds, facts, DAY, tmp_path, **kw)
    ids = f2[0].fact_ids
    assert ids[0] == "I1" and any(i.startswith("bg-s") for i in ids)
    note = next(f for f in facts2 if f.id.startswith("bg-n"))
    assert "Oct 8, 2026" in note.text and note.numbers == [3.5]
    assert not any("Too old" in f.text for f in facts2) and gaps == []
    f3, facts3, _ = bg.enrich(f2, facts2, DAY, tmp_path, **kw)
    assert f3[0].fact_ids == ids and len(facts3) == len(facts2)  # rebuilt, not stacked


def test_failed_fetch_is_a_gap_not_an_error(tmp_path):
    def boom(_):
        raise RuntimeError("yahoo down")

    finds = [finding("ai-1", "x", ["I1"], "ai")]
    f2, facts2, gaps = bg.enrich(
        finds, [fact("I1", "Cerebras (CBRS) up")], DAY, tmp_path, fetch_close=boom, universe=[]
    )
    assert f2[0].fact_ids == ["I1"] and len(facts2) == 1
    assert gaps == ["background: CBRS price history unavailable (yahoo down)"]


@pytest.mark.parametrize("rate", [True, False])
def test_daily_fact_units(rate):
    ref = SeriesRef(kind="daily", provider="fred", id="DGS2" if rate else "DTWEXBGS", label="x")
    f = bg.daily_fact("bg-d1", ref, closes(n=120, start=4.0, step=0.01), date.fromisoformat(DAY))
    assert ("bp" in f.text) is rate and "up on 10 of the last 10 days" in f.text
