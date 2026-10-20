import json

import pytest

from castelino.agents.research.deep import sources
from castelino.agents.weekly.tools import ToolError
from tests.test_research_tools import box


def page(payload: dict) -> str:
    """A Next.js page whose flight data holds `payload`, as Ramp's and OpenRouter's pages do."""
    js = json.dumps("0:" + json.dumps(payload, separators=(",", ":")))[
        1:-1
    ]  # flight JSON is compact
    return f'<html><script>self.__next_f.push([1,"{js}"])</script></html>'


def month(m: str, pct: float, **kw) -> dict:
    return {"date_month": f"2026-{m}-01", "adoption_rate_pct": pct, **kw}


RAMP = page(
    {
        "adoptionOverall": [
            month("03", 52.1, mom_change_pp=0.3, yoy_change_pp=10.0),
            *[
                month(m, v, mom_change_pp=0.4, yoy_change_pp=11.0)
                for m, v in (("04", 53.1), ("05", 53.9), ("06", 54.4), ("07", 54.8), ("08", 55.2))
            ],
            month("09", 55.6, mom_change_pp=0.4, yoy_change_pp=11.7),
        ],
        "adoptionVendor": [
            month("08", 35.0, vendor="OpenAI"),
            month("09", 30.1, vendor="Anthropic"),
            month("09", 35.9, vendor="OpenAI"),
        ],
        "adoptionIndustry": [
            month("09", 70.2, naics_sector="Information"),
            month("09", 31.5, naics_sector="Retail"),
        ],
        "adoptionSize": [
            month("09", 52.0, business_size="Small businesses"),
            month("09", 71.3, business_size="Large businesses"),
        ],
        "tokenPrices": [
            {
                "usage_date": "2026-10-04",
                "token_type": "all_tokens",
                "model_maker": "anthropic",
                "token_cost_usd_7d": 1,
                "token_count_7d": 1,
            },
            {
                "usage_date": "2026-10-11",
                "token_type": "all_tokens",
                "model_maker": "anthropic",
                "token_cost_usd_7d": 75,
                "token_count_7d": 60,
            },
            {
                "usage_date": "2026-10-11",
                "token_type": "all_tokens",
                "model_maker": "openai",
                "token_cost_usd_7d": 25,
                "token_count_7d": 40,
            },
            {
                "usage_date": "2026-10-11",
                "token_type": "output",
                "model_maker": "openai",
                "token_cost_usd_7d": 9,
                "token_count_7d": 9,
            },
        ],
    }
)
RANKINGS = page(
    {
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "DeepSeek V4.1 Flash",
                "item": "https://openrouter.ai/deepseek/deepseek-v4.1-flash",
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Claude Opus 5.5",
                "item": "https://openrouter.ai/anthropic/claude-opus-5.5",
            },
        ]
    }
)
MODELS = json.dumps(
    {
        "data": [
            {
                "id": "deepseek/deepseek-v4.1-flash",
                "hugging_face_id": "deepseek-ai/DeepSeek-V4.1-Flash",
            },
            {"id": "anthropic/claude-opus-5.5", "hugging_face_id": ""},
        ]
    }
)


@pytest.fixture(autouse=True)
def web(monkeypatch):
    pages = {sources.RAMP: RAMP, sources.OPENROUTER: RANKINGS, sources.OPENROUTER_MODELS: MODELS}
    sources._flight.cache_clear()
    monkeypatch.setattr(sources, "_get", lambda url: pages[url])
    return pages


def test_ramp_overall_is_the_last_six_months_dated_and_without_years_as_numbers():
    [f] = sources.ramp("overall")
    assert f.text.startswith("Ramp AI Index, September 2026: 55.6% of U.S. businesses")
    assert "April 2026 53.1%" in f.text and "+0.4 pp" in f.text and "+11.7 pp" in f.text
    assert 55.6 in f.numbers and 53.1 in f.numbers and 11.7 in f.numbers and 2026 not in f.numbers
    assert f.source_url == sources.RAMP and f.provenance == "data"


def test_ramp_vendors_industries_and_sizes_use_the_latest_month_largest_first():
    [v] = sources.ramp("vendors")
    assert "September 2026" in v.text and v.text.index("OpenAI 35.9%") < v.text.index(
        "Anthropic 30.1%"
    )
    assert v.numbers == [35.9, 30.1]
    assert sources.ramp("industries")[0].numbers == [70.2, 31.5]
    assert sources.ramp("sizes")[0].numbers == [71.3, 52.0]


def test_ramp_tokens_are_shares_of_the_latest_week():
    [t] = sources.ramp("tokens")
    assert (
        "week to October 11, 2026" in t.text
        and "Anthropic 60.0%" in t.text
        and "Anthropic 75.0%" in t.text
    )
    assert t.numbers == [60.0, 40.0, 75.0, 25.0]


def test_a_changed_page_or_unknown_view_is_a_tool_error(web):
    with pytest.raises(ToolError, match="view"):
        sources.ramp("weather")
    web[sources.RAMP] = page({"somethingElse": []})
    sources._flight.cache_clear()
    with pytest.raises(ToolError, match="adoptionOverall"):
        sources.ramp("overall")


def test_openrouter_ranks_models_and_tags_open_weights():
    [f] = sources.openrouter()
    assert (
        "1 DeepSeek V4.1 Flash (open weights)" in f.text and "2 Claude Opus 5.5 (closed)" in f.text
    )
    assert "1 of the top 2 are open-weight" in f.text and f.numbers == [1.0, 2.0]
    assert f.source_url == sources.OPENROUTER


def test_the_agents_can_call_both_tools():
    b = box(allowed=["ramp_ai_index", "openrouter_rankings"])
    assert b.call("ramp_ai_index", {"view": "overall"}).startswith(
        "[A1] Ramp AI Index, September 2026"
    )
    assert b.call("openrouter_rankings", {}).startswith("[A2] OpenRouter")
    assert {s["name"] for s in b.specs()} >= {"ramp_ai_index", "openrouter_rankings"}


class FakeIndex:
    """Shaped like adoption.store.AdoptionStore."""

    def periods(self):
        return ["2026-10-12", "2026-10-19"]

    def cells(self, period):
        from castelino.adoption.index import Cell

        return [
            Cell(None, "large", 2, 51.0, 59.3, False),
            Cell(None, "small", 1, 47.9, 47.9, False),
            Cell("Information Technology", "large", 7, 63.3, 64.7, False),
            Cell("Financials", "small", 2, 38.2, 38.2, True),
        ]

    def companies(self, period):
        row = lambda t, b, s, score, talk, hire, spend: dict(  # noqa: E731
            ticker=t, bucket=b, sector=s, score=score, talk_raw=talk, hire_raw=hire, spend_raw=spend
        )
        return [
            row("SOUN", "small", "Information Technology", 80.8, 0.918, 0.2098, 0.55),
            row("NVDA", "large", "Information Technology", 70.8, 1.837, 0.0848, 0.102),
            row("KO", "large", "Consumer Staples", 40.0, 0.0, None, 0.05),
        ]

    def period_stats(self, period):
        return {
            "n_companies": 3,
            "n_scored": 3,
            "n_claims": 10,
            "pillar_coverage": {"talk": 3, "hire": 2, "spend": 3},
        }


NAMES = {"SOUN": "SoundHound AI", "NVDA": "NVIDIA", "KO": "Coca-Cola"}


def test_the_arc_index_becomes_dated_facts_from_its_latest_run():
    facts = sources.arc_index(FakeIndex(), NAMES)
    text = "\n".join(f.text for f in facts)
    assert all(f.text.startswith("ARC AI Adoption Index, run of October 19, 2026") for f in facts)
    assert (
        "large companies average 51.0 and small companies 47.9" in text and "centred on 50" in text
    )
    assert (
        "Information Technology large 63.3 (7 companies)" in text
        and "Financials small 38.2 (2, thin)" in text
    )
    assert (
        "SoundHound AI (SOUN) 21.0%" in text
        and "NVIDIA (NVDA) 1.84" in text
        and "1 of 3 filings" in text
    )
    assert all(f.source_title == "ARC AI Adoption Index" and f.provenance == "data" for f in facts)
    hiring = next(f for f in facts if "AI and ML roles as a share" in f.text)
    assert 21.0 in hiring.numbers and 2026 not in hiring.numbers


def test_an_empty_index_is_a_tool_error():
    class Empty(FakeIndex):
        def periods(self):
            return []

    with pytest.raises(ToolError, match="no run"):
        sources.arc_index(Empty(), NAMES)


def test_the_agents_can_read_the_arc_index(monkeypatch):
    one = sources._fact("ARC AI Adoption Index, run of October 19, 2026: x", [1.0], sources.ARC, "")
    monkeypatch.setattr(sources, "arc_index", lambda: [one])
    b = box(allowed=["arc_ai_adoption_index"])
    assert b.call("arc_ai_adoption_index", {}).startswith(
        "[A1] ARC AI Adoption Index, run of October 19, 2026"
    )
