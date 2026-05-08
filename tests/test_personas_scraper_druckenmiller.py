import asyncio
from datetime import datetime, UTC

from castelino.agents.personas.scrapers.druckenmiller import (
    DruckenmillerScraper, KnownInterview,
)


def test_druckenmiller_fetches_transcript_per_video(monkeypatch):
    scraper = DruckenmillerScraper()

    monkeypatch.setattr(scraper, "_known_interviews", lambda: [
        KnownInterview(video_id="abc123",
                       title="Druckenmiller at Sohn 2018",
                       venue="Sohn Investment Conference",
                       date=datetime(2018, 5, 8, tzinfo=UTC)),
        KnownInterview(video_id="def456",
                       title="Druckenmiller on Bloomberg 2022",
                       venue="Bloomberg",
                       date=datetime(2022, 9, 14, tzinfo=UTC)),
    ])
    monkeypatch.setattr(scraper, "_fetch_transcript",
                        lambda vid: [{"text": f"transcript-for-{vid}"}])

    docs = asyncio.run(scraper.fetch())
    assert len(docs) == 2
    assert "transcript-for-abc123" in docs[0].text
    assert docs[0].date.year == 2018


def test_druckenmiller_persona_id():
    assert DruckenmillerScraper.persona_id == "druckenmiller"


def test_known_interviews_list_nonempty():
    """The hand-curated list ships with at least a few seed interviews
    so production builds aren't empty out of the gate."""
    scraper = DruckenmillerScraper()
    assert len(scraper._known_interviews()) >= 3
