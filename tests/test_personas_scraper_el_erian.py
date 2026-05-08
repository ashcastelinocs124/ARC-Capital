import asyncio
from pathlib import Path

from castelino.agents.personas.scrapers.el_erian import ElErianScraper

FIX = Path(__file__).parent / "fixtures" / "personas"


def test_el_erian_parses_rss_into_corpus_docs(monkeypatch):
    feed_xml = (FIX / "el_erian_feed.xml").read_text()
    scraper = ElErianScraper()
    monkeypatch.setattr(scraper, "_fetch_feed", lambda url: feed_xml)
    async def _fake_get_article(url: str) -> str:
        return f"<html><body><article>el-erian body for {url}</article></body></html>"
    monkeypatch.setattr(scraper, "_fetch_article", _fake_get_article)

    docs = asyncio.run(scraper.fetch())
    assert len(docs) >= 1
    assert "el-erian body" in docs[0].text


def test_el_erian_persona_id():
    assert ElErianScraper.persona_id == "el_erian"
