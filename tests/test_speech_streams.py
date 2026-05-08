from pathlib import Path
from castelino.triggers.speech.streams import (
    parse_fomc_live_url, FOMC_MONETARY_POLICY_PAGE,
)

FIX = Path(__file__).parent / "fixtures" / "fed"

def test_parse_fomc_live_url_finds_youtube_link():
    html = (FIX / "monetary_policy_page.html").read_text()
    url = parse_fomc_live_url(html)
    assert url is not None
    assert "youtube" in url or "youtu.be" in url

def test_parse_fomc_live_url_returns_none_when_no_link():
    assert parse_fomc_live_url("<html><body>nothing</body></html>") is None
