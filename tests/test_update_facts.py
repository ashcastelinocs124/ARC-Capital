from castelino.agents.update.facts import (
    drafts_prompt,
    facts_from_search,
    numbers_in,
    to_findings,
)
from castelino.agents.update.models import Fact, FindingDraft, FindingDrafts, SeriesRef


def test_numbers_in_handles_commas_signs_and_unicode_minus():
    assert numbers_in("SPY +0.81%, claims 220,000, oil −1.5%") == [0.81, 220000.0, -1.5]


def test_facts_from_search_one_per_cited_line_and_strips_links():
    text = (
        "- Oil rose 4% after OPEC cut output ([reuters.com](https://r.com/2026/10/07/x))\n"
        "- An uncited line with 9%\n"
        "- Stocks gained 0.8% ([cnbc.com](https://c.com/a))"
    )
    first = text.index("([reuters")
    second = text.index("([cnbc")
    cites = [
        ("Reuters", "https://r.com/2026/10/07/x", first, first + 40),
        ("CNBC", "https://c.com/a", second, second + 20),
    ]
    facts = facts_from_search("N", text, cites)
    assert [f.id for f in facts] == ["N1", "N2"]
    assert facts[0].text == "Oil rose 4% after OPEC cut output" and facts[0].numbers == [4.0]
    assert facts[0].source_title == "Reuters" and facts[0].provenance == "reported"
    assert facts[1].numbers == [0.8]


def test_no_citations_gives_no_facts():
    assert facts_from_search("N", "Oil rose 4%", []) == []


def test_to_findings_drops_unknown_fact_ids_and_caps():
    ref = SeriesRef(kind="daily", provider="fred", id="DGS10", label="10y")
    facts = [
        Fact(
            id="M1",
            text="10y 5.27%",
            numbers=[5.27],
            provenance="data",
            series=ref,
            source_title="FRED DGS10",
            source_url="u",
        )
    ]
    drafts = FindingDrafts(
        findings=[
            FindingDraft(claim="10y up", figure=5.27, unit="%", fact_ids=["M1", "M9"]),
            FindingDraft(claim="bogus", figure=None, unit="", fact_ids=["M9"]),
            FindingDraft(claim="again", figure=None, unit="", fact_ids=["M1"]),
        ]
    )
    out = to_findings(drafts, facts, "macro", cap=1)
    assert len(out) == 1 and out[0].id == "macro-1" and out[0].fact_ids == ["M1"]
    assert out[0].series == ref and out[0].source_title == "FRED DGS10"


def test_drafts_prompt_includes_ask_and_ids():
    f = Fact(
        id="M1",
        text="CPI 3.71%",
        numbers=[3.71],
        provenance="data",
        source_title="FRED",
        source_url="u",
    )
    p = drafts_prompt([f], "focus on inflation", "check shelter", 6)
    assert "[M1] CPI 3.71%" in p and "check shelter" in p and "at most 6" in p


def test_bare_url_digits_are_not_numbers():
    text = "- Oil rose 3% per https://x.com/2026/10/07/oil ([r](https://r.com/a))"
    i = text.index("([r]")
    facts = facts_from_search("N", text, [("R", "https://r.com/a", i, i + 5)])
    assert facts[0].numbers == [3.0] and "https://" not in facts[0].text


def test_untitled_citation_shows_the_site_name():
    text = "- Oil rose 3% ([r](https://www.fidelity.com/news/x?utm_source=openai))"
    url = "https://www.fidelity.com/news/x?utm_source=openai"
    i = text.index("([r]")
    facts = facts_from_search("N", text, [(url, url, i, i + 5)])
    assert facts[0].source_title == "fidelity.com" and facts[0].source_url == url
