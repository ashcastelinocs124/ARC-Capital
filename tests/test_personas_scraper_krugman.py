import asyncio
from pathlib import Path

from castelino.agents.personas.scrapers.krugman import KrugmanScraper

FIX = Path(__file__).parent / "fixtures" / "personas"


def test_krugman_parses_rss_into_corpus_docs(monkeypatch):
    feed_xml = (FIX / "krugman_feed.xml").read_text()
    scraper = KrugmanScraper()

    monkeypatch.setattr(scraper, "_fetch_feed", lambda url: feed_xml)
    # Stub article-page fetch — just return a deterministic body
    async def _fake_get_article(url: str) -> str:
        return f"<html><body><article>full body for {url}</article></body></html>"
    monkeypatch.setattr(scraper, "_fetch_article", _fake_get_article)

    docs = asyncio.run(scraper.fetch())
    assert len(docs) >= 1
    d = docs[0]
    assert d.url.startswith("http")
    assert "full body" in d.text
    assert d.date.year >= 2020


def test_krugman_persona_id():
    assert KrugmanScraper.persona_id == "krugman"
