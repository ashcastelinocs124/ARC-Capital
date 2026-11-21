"""Market sentiment in the Daily Update: the facts code builds and the guard rules on how they're used."""

from datetime import UTC, date, datetime

from castelino.agents.update import sentiment
from castelino.agents.update.guard import check_note
from castelino.agents.update.models import Fact, Finding, MorningNote, NoteItem
from castelino.signals.fear_greed import FearGreed, FGComponent
from castelino.signals.sector_sentiment import (
    SectorExplanation,
    SectorScore,
    SectorSentimentSnapshot,
    StockContribution,
    StockRow,
)

DAY = "2026-10-14"
TODAY = lambda: date(2026, 10, 14)  # noqa: E731


def stock(sym, name):
    return StockRow(symbol=sym, name=name, sector="Semiconductors", market_cap=1e12, rsi14=None, macd_hist=None, vs_sma50=None, vs_sma200=None, ret_3m=None, rev_yoy=None, earnings_growth=None, pe_rel=None)  # fmt: skip


def needle(score=29, previous=37):
    return FearGreed(
        score=score, zone="Fear", as_of=date(2026, 10, 14), previous=previous, week_ago=41, month_ago=40,
        components=[
            FGComponent(key="momentum", name="Market momentum", score=24, raw="S&P 500 2.5% above its 125-day average", previous=26, week_ago=30),
            FGComponent(key="junk", name="Junk bond demand", score=17, raw="High-yield spread 3.16%, +45 bp in a month", previous=25, week_ago=41),
        ],
    )  # fmt: skip


def snapshot():
    semis = SectorScore(
        sector="Semiconductors", etf="SMH", part_of="Technology", divergence=-0.333, tech_score=-0.4, fund_score=0.05,
        label="fearful", fg_score=22, delta_since_prev=-0.06,
        explanation=SectorExplanation(verdict="sector_wide", n_agree=7, n_total=10, top_symbol="NVDA", top_share=0.3,
            equal_weight_divergence=-0.3, contributions=[StockContribution(symbol="NVDA", divergence=-0.4, contribution=-0.1)], drivers=["NVDA"]),
    )  # fmt: skip
    energy = SectorScore(sector="Energy", etf="XLE", divergence=0.1, tech_score=0.12, fund_score=0.02, label="fair", fg_score=58)  # fmt: skip
    return SectorSentimentSnapshot(
        as_of=datetime(2026, 10, 14, 13, 35, tzinfo=UTC),
        sectors=[energy, semis],
        stocks=[stock("NVDA", "NVIDIA"), stock("AMD", "Advanced Micro Devices")],
        fear_greed=needle(score=33, previous=37),  # the 09:30 reading, before today's close
    )


def news():
    return Finding(id="news-1", agent="news", claim="Chip stocks fell", provenance="reported", source_title="s", source_url="u", fact_ids=["N1"])  # fmt: skip


def test_the_readings_become_explaining_facts_and_one_finding():
    asked = []
    compute = lambda stocks: asked.append(stocks) or needle()  # noqa: E731
    f, x, gaps = sentiment.add([news()], [], DAY, today=TODAY, load=snapshot, compute=compute)
    assert asked == [["AMD", "NVDA"]] and gaps == []  # recomputed from the snapshot's stocks
    assert [i.id for i in x] == [f"sent{n}" for n in range(1, 7)]
    assert x[0].text.startswith("How to read ARC's sentiment gauges")
    assert x[1].text == (
        "ARC Fear & Greed closed Wednesday, October 14 at 29 of 100 (Fear); 37 (Fear) the session "
        "before; 41 (Fear) a week ago; 40 (Fear) a month ago."
    )
    # the signal that moved most comes first, so the Editor can name what drove the needle
    assert x[2].text == (
        "Fear & Greed signal, Junk bond demand: 17 of 100, from 25 the session before and 41 a week "
        "ago (High-yield spread 3.16%, +45 bp in a month)."
    )
    assert {3.16, 45, 17, 41} <= set(x[2].numbers)
    # strongest sector first; its mood, the price-vs-fundamentals split and how broad it is, in words
    assert x[4].text == (
        "Sector Sentiment, Semiconductors, within Technology, as of October 14 09:35 ET: 22 of "
        "100, fearful: prices have fallen further than the earnings outlook; 27 at the previous "
        "reading; price trend weak, fundamentals about average; sector-wide, 7 of its 10 largest "
        "stocks lean the same way."
    )
    assert [i.id for i in f] == ["news-1", "sent-1"]
    assert (
        f[1].claim
        == "Market sentiment: ARC's Fear & Greed needle closed at 29 (Fear), from 37 the session before."
    )
    assert f[1].fact_ids == [i.id for i in x] and f[1].figure == 29

    f2, x2, _ = sentiment.add(f, x, DAY, today=TODAY, load=snapshot, compute=lambda s: needle())
    assert [i.id for i in f2] == ["news-1", "sent-1"] and len(
        x2
    ) == 6  # a rebuild never stacks them


def test_a_past_day_keeps_its_saved_facts_and_a_failed_recompute_uses_the_stored_needle():
    old = [
        Fact(
            id="sent1",
            text="saved",
            numbers=[1],
            provenance="data",
            source_title="s",
            source_url="u",
        )
    ]
    boom = lambda s: (_ for _ in ()).throw(AssertionError("must not recompute a past day"))  # noqa: E731
    assert sentiment.add([news()], old, "2026-10-13", today=TODAY, compute=boom)[1] == old

    def offline(stocks):
        raise RuntimeError("Yahoo down")

    f, x, gaps = sentiment.add([], [], DAY, today=TODAY, load=snapshot, compute=offline)
    assert "at 33 of 100" in x[1].text and "Yahoo down" in gaps[0]  # the stored needle, dated
    assert sentiment.add([], [], DAY, today=TODAY, load=lambda: None)[2] == [
        "market sentiment: no Sector Sentiment snapshot"
    ]


def note_with(*items):
    return MorningNote(headline="Chips fall", takeaways=["a", "b", "c"], items=list(items), themes_touched=[], new_themes=[])  # fmt: skip


def test_guard_checks_sentiment_scores_and_keeps_sentiment_off_its_own_item():
    f, x, _ = sentiment.add(
        [news()], [], DAY, today=TODAY, load=snapshot, compute=lambda s: needle()
    )
    explained = (
        "Chip stocks fell. The selling was as much about mood as the outlook: the Fear & Greed needle "
        "closed at 29, down from 37, as junk bond demand fell to 17. Semiconductors read 22 of 100."
    )
    ok = NoteItem(
        rank=1, title="Chips fall", body=explained, finding_ids=["news-1", "sent-1"], chart=None
    )
    assert check_note(note_with(ok), f, x, items=1) == []

    wrong = ok.model_copy(
        update={"body": explained.replace("at 29", "at 31").replace("22 of", "23 of")}
    )
    assert check_note(note_with(wrong), f, x, items=1) == [
        "item 1: sentiment score 31",
        "item 1: sentiment score 23",
    ]
    uncited = ok.model_copy(update={"finding_ids": ["news-1"]})  # ARC's numbers need sent-1
    assert "item 1: sentiment score 29" in check_note(note_with(uncited), f, x, items=1)

    alone = ok.model_copy(update={"finding_ids": ["sent-1"]})
    assert check_note(note_with(alone), f, x, items=1) == [
        "item 1 rests only on the Market sentiment finding; sentiment explains another item's "
        "move, it is never an item of its own"
    ]
