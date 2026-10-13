import pandas as pd
import pytest

from castelino.agents.update import exhibits
from castelino.agents.update.guard import clean_picks, pick_errors
from castelino.agents.update.models import (
    Fact,
    Finding,
    ItemExhibit,
    MorningNote,
    NoteItem,
    NotePoint,
    Point,
    SeriesRef,
)

DAILY = SeriesRef(kind="daily", provider="yahoo", id="CBRS", label="Cerebras")
HIST = SeriesRef(
    kind="release", provider="fred", id="CPIAUCSL", label="CPI y/y",
    points=[Point(label=m, value=v) for m, v in zip("JFMAMJ", [3.0, 3.2, 3.1, 3.6, 3.7, 3.8], strict=True)],
)  # fmt: skip
FACTS = [
    Fact(id="I1", text="moves", numbers=[1.68, 0.97, -0.23], provenance="reported", source_title="Nasdaq", source_url="u"),
    Fact(id="bg-s1", text="range", numbers=[149.08, 12.4, 31.8, 158.9, 71.2, 6.18], provenance="data", series=DAILY, source_title="Yahoo Finance CBRS", source_url="u"),
    Fact(id="bg-d1", text="cpi", numbers=[3.0, 3.2, 3.1, 3.6, 3.7, 3.8], provenance="data", series=HIST, source_title="FRED CPIAUCSL", source_url="u"),
    Fact(id="N1", text="eps", numbers=[5.57, 5.93], provenance="reported", source_title="Reuters", source_url="u"),
]  # fmt: skip
FINDS = [
    Finding(id="ai-1", agent="ai", claim="c", provenance="data", source_title="s", source_url="u", fact_ids=["I1", "bg-s1", "bg-d1", "N1"]),
    Finding(id="news-1", agent="news", claim="c", provenance="data", source_title="s", source_url="u", fact_ids=["N1"], series=DAILY),
]  # fmt: skip


def pts(*xs):
    return [NotePoint(fact_id=f, label=lab, value=v) for f, lab, v in xs]


PICKS = {
    "range": ItemExhibit(kind="range", title="Cerebras sits near its high", fact_ids=[], window_days=30, unit="$",
                         points=pts(("bg-s1", "52-week low", 71.2), ("bg-s1", "Last", 149.08), ("bg-s1", "52-week high", 158.9))),
    "movers": ItemExhibit(kind="movers", title="Cerebras beat the chip leaders", fact_ids=[], window_days=30, unit="%",
                          points=pts(("I1", "Cerebras", 1.68), ("I1", "Nvidia", 0.97), ("I1", "Semis", -0.23))),
    "bars": ItemExhibit(kind="bars", title="Odds by outcome", fact_ids=[], window_days=30, unit="%",
                        points=pts(("I1", "3.7%", 1.68), ("I1", "3.8%", 0.97))),
    "ladder": ItemExhibit(kind="ladder", title="The rally built for months", fact_ids=[], window_days=30, unit="%",
                          points=pts(("bg-s1", "1 month", 12.4), ("bg-s1", "3 months", 31.8))),
    "columns": ItemExhibit(kind="columns", title="Inflation rose three months running", fact_ids=["bg-d1"], window_days=30, unit="%", points=[]),
    "dumbbell": ItemExhibit(kind="dumbbell", title="Estimate to actual", fact_ids=[], window_days=30, unit="$",
                            points=pts(("N1", "Estimate", 5.93), ("N1", "Actual", 5.57))),
    "vs_expected": ItemExhibit(kind="vs_expected", title="JPMorgan earned less than expected", fact_ids=[], window_days=30, unit="$",
                               points=pts(("N1", "Estimate", 5.93), ("N1", "Actual", 5.57))),
    "compare": ItemExhibit(kind="compare", title="Cerebras vs itself", fact_ids=["bg-s1", "bg-s1"], window_days=30, unit="%", points=[]),
    "line": ItemExhibit(kind="line", title="Cerebras over a month", fact_ids=["bg-s1"], window_days=30, unit="$", points=[]),
}  # fmt: skip


def item(pick, rank=1, chart="news-1"):
    return NoteItem(
        rank=rank, title="t", body="b", finding_ids=["ai-1", "news-1"], chart=chart, exhibit=pick
    )


@pytest.mark.parametrize("kind", [k for k in PICKS if k != "compare"])
def test_valid_picks_pass(kind):
    assert pick_errors(item(PICKS[kind]), FINDS, FACTS) == []


def test_bad_picks_are_named():
    wrong = PICKS["movers"].model_copy(
        update={"points": pts(("I1", "Cerebras", 2.5), ("I1", "Nvidia", 0.97))}
    )
    assert any("2.5 is not a number of I1" in e for e in pick_errors(item(wrong), FINDS, FACTS))
    foreign = PICKS["columns"].model_copy(update={"fact_ids": ["X9"]})
    assert "X9 is not one of the item's facts" in pick_errors(item(foreign), FINDS, FACTS)
    flat = PICKS["columns"].model_copy(update={"fact_ids": ["N1"]})
    assert "columns needs one fact with a release history" in pick_errors(item(flat), FINDS, FACTS)
    upside = PICKS["range"].model_copy(update={"points": list(reversed(PICKS["range"].points))})
    assert "range points must be [low, last, high]" in pick_errors(item(upside), FINDS, FACTS)
    titled = PICKS["range"].model_copy(update={"title": "Up 99% this year"})
    assert any(e.startswith("title:") for e in pick_errors(item(titled), FINDS, FACTS))


def test_clean_picks_drops_only_bad_ones():
    bad = PICKS["range"].model_copy(update={"points": PICKS["range"].points[:2]})
    note = MorningNote(headline="h", takeaways=[], items=[item(bad, 1), item(PICKS["ladder"], 2)],
                       themes_touched=[], new_themes=[])  # fmt: skip
    out = clean_picks(note, FINDS, FACTS)
    assert out.items[0].exhibit is None and out.items[1].exhibit == PICKS["ladder"]


def fake_fetch(ref, window_days=None):
    return [(f"d{i}", 100 + i) for i in range(8)]


def fake_series(ref, window_days):
    return pd.Series(
        range(100, 110), index=pd.bdate_range(end="2026-10-13", periods=10), dtype=float
    )


def test_every_form_draws_a_png_and_bad_ones_fall_back_to_line(tmp_path):
    items = [item(p, rank=i) for i, p in enumerate(PICKS.values(), 1)]
    broken = PICKS["columns"].model_copy(update={"fact_ids": ["N1"]})  # no history: can't draw
    items.append(item(broken, rank=len(items) + 1))
    note = MorningNote(headline="h", takeaways=[], items=items, themes_touched=[], new_themes=[])
    out = exhibits.make_note_exhibits(note, FINDS, FACTS, tmp_path, fake_fetch, fake_series)
    assert [e.item for e in out] == list(range(1, len(items) + 1))
    assert all((tmp_path / e.file).stat().st_size > 10_000 for e in out)
    assert out[-1].title.startswith(
        "Exhibit 10: Cerebras"
    )  # fallback line chart of news-1's series
    rng = next(e for e in out if e.item == 1)
    assert rng.title == "Exhibit 1: Cerebras sits near its high" and "% of the way" in rng.subtitle
    cols = next(e for e in out if e.item == 5)
    assert "3 straight rises to 3.80%" in cols.subtitle
