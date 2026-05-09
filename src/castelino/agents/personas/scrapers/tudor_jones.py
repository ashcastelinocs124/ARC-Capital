"""Scrape Paul Tudor Jones interview transcripts from YouTube.

PTJ has no public RSS — we hand-curate a list of well-known long-form
interviews (Robin Hood Foundation, Davos, Real Vision, CNBC) and pull
each transcript via youtube-transcript-api. Add to KNOWN_INTERVIEWS
manually as new pieces are published.

Sonar fallback fires when curated interviews yield < 3 docs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from castelino.agents.personas.corpus import CorpusDoc
from castelino.agents.personas.scrapers.base import PersonaScraper
from castelino.agents.personas.sonar_fetcher import fetch_persona_via_sonar


@dataclass(frozen=True)
class KnownInterview:
    video_id: str
    title: str
    venue: str
    date: datetime


# Seed list. Replace placeholder video_ids with real ones as discovered.
KNOWN_INTERVIEWS: list[KnownInterview] = [
    KnownInterview(
        video_id="PLACEHOLDER_RH_2022",
        title="Paul Tudor Jones at Robin Hood 2022",
        venue="Robin Hood Foundation",
        date=datetime(2022, 11, 1, tzinfo=UTC),
    ),
    KnownInterview(
        video_id="PLACEHOLDER_DAVOS_2023",
        title="Paul Tudor Jones at Davos 2023",
        venue="World Economic Forum",
        date=datetime(2023, 1, 18, tzinfo=UTC),
    ),
    KnownInterview(
        video_id="PLACEHOLDER_RV_2024",
        title="Paul Tudor Jones on Real Vision 2024",
        venue="Real Vision",
        date=datetime(2024, 3, 15, tzinfo=UTC),
    ),
]


class TudorJonesScraper(PersonaScraper):
    persona_id = "tudor_jones"

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
                    source=f"tudor_jones_{iv.date.strftime('%Y%m%d')}_{iv.venue.lower().replace(' ', '_')}",
                    date=iv.date,
                    title=iv.title,
                    text=text,
                    url=f"https://www.youtube.com/watch?v={iv.video_id}",
                ))
            except Exception:
                continue

        if len(docs) < 3:
            docs.extend(fetch_persona_via_sonar(
                persona_id=self.persona_id, persona_name="Paul Tudor Jones",
            ))
        return docs
