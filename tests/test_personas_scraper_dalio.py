"""Unit tests for DalioScraper — mocks all HTTP."""
import asyncio

import castelino.agents.personas.scrapers.dalio as mod
from castelino.agents.personas.scrapers.dalio import DalioScraper


def test_dalio_persona_id():
    assert DalioScraper.persona_id == "dalio"


def test_dalio_empty_known_urls_falls_to_sonar(monkeypatch):
    """With no known URLs and Sonar mocked out, returns empty list."""
    scraper = DalioScraper()
    monkeypatch.setattr(scraper, "_known_urls", lambda: [])
    monkeypatch.setattr(mod, "fetch_persona_via_sonar", lambda **kw: [])

    docs = asyncio.run(scraper.fetch())
    assert docs == []


def test_dalio_skips_short_article_text(monkeypatch):
    """Articles whose parsed text is < 50 chars are filtered out."""
    scraper = DalioScraper()
    monkeypatch.setattr(scraper, "_known_urls", lambda: ["https://bridgewater.com/fake"])

    async def _tiny_html(url):
        return "<html><body><article>short</article></body></html>"

    monkeypatch.setattr(scraper, "_fetch_article", _tiny_html)
    monkeypatch.setattr(mod, "fetch_persona_via_sonar", lambda **kw: [])

    docs = asyncio.run(scraper.fetch())
    assert docs == []


def test_dalio_builds_corpus_doc_from_article(monkeypatch):
    url = "https://www.bridgewater.com/research-and-insights/the-changing-world-order"
    scraper = DalioScraper()
    monkeypatch.setattr(scraper, "_known_urls", lambda: [url])

    async def _full_html(u):
        return (
            "<html><body><article>"
            + "Ray Dalio on the changing world order and debt cycles. " * 5
            + "</article></body></html>"
        )

    monkeypatch.setattr(scraper, "_fetch_article", _full_html)
    monkeypatch.setattr(mod, "fetch_persona_via_sonar", lambda **kw: [])

    docs = asyncio.run(scraper.fetch())
    assert len(docs) == 1
    d = docs[0]
    assert d.url == url
    assert d.source.startswith("bridgewater_")
    assert len(d.text) >= 50


def test_dalio_fetch_error_skips_url(monkeypatch):
    """Network errors on individual URLs are swallowed; others still processed."""
    urls = [
        "https://bridgewater.com/bad",
        "https://bridgewater.com/good",
    ]
    scraper = DalioScraper()
    monkeypatch.setattr(scraper, "_known_urls", lambda: urls)

    async def _conditional(url):
        if "bad" in url:
            raise OSError("connection refused")
        return "<html><body><article>" + "Dalio macro views. " * 10 + "</article></body></html>"

    monkeypatch.setattr(scraper, "_fetch_article", _conditional)
    monkeypatch.setattr(mod, "fetch_persona_via_sonar", lambda **kw: [])

    docs = asyncio.run(scraper.fetch())
    assert len(docs) == 1
    assert "good" in docs[0].url
