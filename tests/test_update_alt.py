from castelino.agents import base
from castelino.agents.update import alt
from castelino.agents.update.models import FindingDraft, FindingDrafts
from castelino.agents.update.sources import polymarket

EVENTS = [
    {
        "title": "Fed Decision in December?",
        "slug": "fed-dec",
        "markets": [
            {
                "question": "Fed cuts 25bp in December?",
                "active": True,
                "closed": False,
                "outcomePrices": '["0.41", "0.59"]',
                "clobTokenIds": '["tokA", "tokB"]',
                "oneDayPriceChange": -0.05,
                "oneWeekPriceChange": -0.17,
            },
            {
                "question": "Fed hikes?",
                "active": True,
                "closed": False,
                "outcomePrices": '["0.02", "0.98"]',
                "clobTokenIds": '["tokC", "tokD"]',
                "oneDayPriceChange": None,
                "oneWeekPriceChange": 0.001,
            },
            {
                "question": "closed one",
                "active": True,
                "closed": True,
                "outcomePrices": '["0.5", "0.5"]',
                "clobTokenIds": '["x", "y"]',
            },
            {"question": "broken", "active": True, "closed": False, "outcomePrices": "nope"},
        ],
    }
]


def drafts(*ids):
    return FindingDrafts(
        findings=[FindingDraft(claim=f"c {i}", figure=None, unit="", fact_ids=[i]) for i in ids]
    )


def test_polymarket_facts_rank_by_move_and_skip_bad_markets():
    facts = polymarket.facts(EVENTS, top=8)
    assert [f.id for f in facts] == ["P1", "P2"]
    p1 = facts[0]
    assert "Fed cuts 25bp in December?" in p1.text and p1.series.id == "tokA"
    assert p1.numbers == [25.0, 41.0, -5.0, -17.0]  # "25bp" from the question
    assert p1.source_url == "https://polymarket.com/event/fed-dec"


def test_price_history_parses():
    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"history": [{"t": 1, "p": 0.5}, {"t": 2, "p": 0.41}]}

    assert polymarket.price_history("tokA", get=lambda *a, **k: R()) == [(1, 0.5), (2, 0.41)]


def test_run_combines_polymarket_and_x(monkeypatch):
    fake = base.FakeLLMClient()
    fake.register("FindingDrafts", lambda s, u: drafts("P1", "X1"))
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    text = "- Macro X argues inflation is sticky ([x.com](https://x.com/a))"
    i = text.index("([x.com")
    out = alt.run(
        "fed",
        events_fn=lambda: EVENTS,
        search=lambda s, u, model=None: (text, [("X post", "https://x.com/a", i, i + 5)]),
    )
    assert [f.agent for f in out.findings] == ["alt", "alt"]
    assert out.findings[0].series.provider == "polymarket"
    assert out.findings[1].provenance == "reported"


def test_run_survives_one_source_failing(monkeypatch):
    fake = base.FakeLLMClient()
    fake.register("FindingDrafts", lambda s, u: drafts("P1"))
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)

    def boom(*a, **k):
        raise RuntimeError("search down")

    out = alt.run("fed", events_fn=lambda: EVENTS, search=boom)
    assert len(out.findings) == 1


def test_question_figures_are_allowed_numbers_and_missing_moves_are_not_zero():
    ev = [
        {
            "title": "Fed Decision in December?",
            "slug": "fed-dec",
            "markets": [
                {
                    "question": "Fed decreases rates by 25 bps after December meeting?",
                    "active": True,
                    "closed": False,
                    "outcomePrices": '["0.62", "0.38"]',
                    "clobTokenIds": '["tokA", "tokB"]',
                    "oneDayPriceChange": None,
                    "oneWeekPriceChange": 0.07,
                }
            ],
        }
    ]
    f = polymarket.facts(ev)[0]
    assert 25.0 in f.numbers and 62.0 in f.numbers and 7.0 in f.numbers
    assert 0.0 not in f.numbers and "1d" not in f.text
