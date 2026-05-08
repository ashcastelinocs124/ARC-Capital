import asyncio
from castelino.agents.personas.scrapers.buffett import BuffettScraper


def test_buffett_scraper_extracts_year_from_url(monkeypatch):
    scraper = BuffettScraper()
    assert scraper._year_from_url(
        "https://www.berkshirehathaway.com/letters/2008ltr.pdf"
    ) == 2008


def test_buffett_scraper_fetch_returns_corpus_docs(monkeypatch):
    scraper = BuffettScraper()

    # Override: return only one URL
    monkeypatch.setattr(
        scraper, "_known_letter_urls",
        lambda: ["https://www.berkshirehathaway.com/letters/2008ltr.pdf"],
    )

    # Override: skip the network — return synthetic response
    class _R:
        status_code = 200
        content = b"%PDF-fake"

    async def _fake_get(url):
        return _R()
    monkeypatch.setattr(scraper, "_fetch_pdf", _fake_get)

    # Override: bypass real PDF parsing — return a deterministic string
    monkeypatch.setattr(
        scraper, "_parse_pdf_bytes",
        lambda content: "shareholders of Berkshire, this year was strong",
    )

    docs = asyncio.run(scraper.fetch())
    assert len(docs) == 1
    d = docs[0]
    assert d.source == "2008ltr.pdf"
    assert d.date.year == 2008
    assert "Berkshire" in d.text


def test_buffett_scraper_skips_non_200(monkeypatch):
    scraper = BuffettScraper()
    monkeypatch.setattr(
        scraper, "_known_letter_urls",
        lambda: ["https://x/2008ltr.pdf", "https://x/2009ltr.pdf"],
    )

    class _OK:
        status_code = 200
        content = b"%PDF"
    class _Bad:
        status_code = 404
        content = b""

    calls = {"n": 0}
    async def _fake_get(url):
        calls["n"] += 1
        return _OK() if "2008" in url else _Bad()
    monkeypatch.setattr(scraper, "_fetch_pdf", _fake_get)
    monkeypatch.setattr(scraper, "_parse_pdf_bytes", lambda c: "ok")

    docs = asyncio.run(scraper.fetch())
    assert len(docs) == 1
    assert docs[0].date.year == 2008
