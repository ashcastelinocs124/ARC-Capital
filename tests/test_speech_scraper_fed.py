from pathlib import Path

from castelino.triggers.figure_deviation.scrapers.fed import (
    parse_speech_index,
    parse_speech_page,
)

FIXTURES = Path(__file__).parent / "fixtures" / "fed"


def test_parse_speech_page_extracts_text_and_metadata():
    html = (FIXTURES / "powell_2026-03-01_brookings.html").read_text()
    parsed = parse_speech_page(html, url="https://example/2026/powell.htm")
    assert "Powell" in parsed.speaker
    assert parsed.date.year == 2026
    assert len(parsed.text) > 100


def test_parse_speech_index_returns_links():
    html = (FIXTURES / "speech_index_2026.html").read_text()
    items = parse_speech_index(html, base_url="https://federalreserve.gov")
    assert len(items) >= 1
    assert all(item.url.startswith("https://") for item in items)
    assert all(item.speaker for item in items)
