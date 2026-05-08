import asyncio
from pathlib import Path

from castelino.agents.personas.scrapers.summers import SummersScraper

FIX = Path(__file__).parent / "fixtures" / "personas"


def test_summers_parses_rss_and_brookings(monkeypatch):
    feed_xml = (FIX / "summers_feed.xml").read_text()
    scraper = SummersScraper()
    monkeypatch.setattr(scraper, "_fetch_feed", lambda url: feed_xml)
    monkeypatch.setattr(scraper, "_brookings_urls", lambda: [
        "https://www.brookings.edu/articles/synthetic-summers-paper",
    ])
    async def _fake_get_article(url: str) -> str:
        return f"<html><body><article>summers body for {url}</article></body></html>"
    monkeypatch.setattr(scraper, "_fetch_article", _fake_get_article)

    docs = asyncio.run(scraper.fetch())
    # 2 from RSS + 1 from Brookings list
    assert len(docs) >= 2
    assert any("brookings" in d.url for d in docs)


def test_summers_persona_id():
    assert SummersScraper.persona_id == "summers"
