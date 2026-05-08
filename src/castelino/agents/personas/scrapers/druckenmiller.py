"""Scrape Stanley Druckenmiller interview transcripts from YouTube.

No public RSS for him — we hand-curate a list of well-known long-form
interviews (Sohn, Robin Hood, Real Vision, Bloomberg, CNBC) and pull
each transcript via youtube-transcript-api. Add to KNOWN_INTERVIEWS
manually as new pieces are published.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from castelino.agents.personas.corpus import CorpusDoc
from castelino.agents.personas.scrapers.base import PersonaScraper


@dataclass(frozen=True)
class KnownInterview:
    video_id: str
    title: str
    venue: str
    date: datetime


# Seed list. Replace placeholder video_ids with real ones (these are the
# kind of interviews to track: Sohn pitches, Robin Hood, Real Vision
# long-forms, periodic Bloomberg / CNBC appearances).
KNOWN_INTERVIEWS: list[KnownInterview] = [
    KnownInterview(
        video_id="PLACEHOLDER_SOHN_2022", title="Druckenmiller at Sohn 2022",
        venue="Sohn Investment Conference",
        date=datetime(2022, 6, 8, tzinfo=UTC),
    ),
    KnownInterview(
        video_id="PLACEHOLDER_RH_2023", title="Druckenmiller at Robin Hood 2023",
        venue="Robin Hood Foundation",
        date=datetime(2023, 10, 12, tzinfo=UTC),
    ),
    KnownInterview(
        video_id="PLACEHOLDER_RV_2024", title="Druckenmiller on Real Vision",
        venue="Real Vision",
        date=datetime(2024, 4, 22, tzinfo=UTC),
    ),
]


class DruckenmillerScraper(PersonaScraper):
    persona_id = "druckenmiller"

    def _known_interviews(self) -> list[KnownInterview]:
        return list(KNOWN_INTERVIEWS)

    def _fetch_transcript(self, video_id: str) -> list[dict]:
        # Lazy-import so unit tests that monkeypatch this method don't
        # require youtube-transcript-api to be installed.
        from youtube_transcript_api import YouTubeTranscriptApi
        return YouTubeTranscriptApi.get_transcript(video_id)

    async def fetch(self) -> list[CorpusDoc]:
        docs: list[CorpusDoc] = []
        for iv in self._known_interviews():
            try:
                segments = self._fetch_transcript(iv.video_id)
                text = " ".join(s.get("text", "") for s in segments).strip()
                if not text:
                    continue
                docs.append(CorpusDoc(
                    source=f"druckenmiller_{iv.date.strftime('%Y%m%d')}_{iv.venue.lower().replace(' ', '_')}",
                    date=iv.date,
                    title=iv.title,
                    text=text,
                    url=f"https://www.youtube.com/watch?v={iv.video_id}",
                ))
            except Exception:
                # Skip videos that have transcripts disabled or other issues.
                continue
        return docs
