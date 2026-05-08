"""Scrape Berkshire Hathaway annual shareholder letters."""
from __future__ import annotations

import re
from datetime import datetime, UTC
from io import BytesIO

import httpx

from castelino.agents.personas.corpus import CorpusDoc
from castelino.agents.personas.scrapers.base import PersonaScraper


class BuffettScraper(PersonaScraper):
    persona_id = "buffett"
    BASE = "https://www.berkshirehathaway.com/letters/"
    FIRST_YEAR = 1977

    def _known_letter_urls(self) -> list[str]:
        now = datetime.now(UTC).year
        return [f"{self.BASE}{y}ltr.pdf" for y in range(self.FIRST_YEAR, now)]

    async def _fetch_pdf(self, url: str):
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.get(url)

    def _parse_pdf_bytes(self, content: bytes) -> str:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(content))
        return "\n".join(p.extract_text() or "" for p in reader.pages)

    def _year_from_url(self, url: str) -> int:
        m = re.search(r"(\d{4})ltr\.", url)
        return int(m.group(1)) if m else 1900

    async def fetch(self) -> list[CorpusDoc]:
        docs: list[CorpusDoc] = []
        for url in self._known_letter_urls():
            try:
                r = await self._fetch_pdf(url)
                if r.status_code != 200:
                    continue
                text = self._parse_pdf_bytes(r.content)
                if not text.strip():
                    continue
                year = self._year_from_url(url)
                docs.append(CorpusDoc(
                    source=url.rsplit("/", 1)[-1],
                    date=datetime(year, 12, 31, tzinfo=UTC),
                    title=f"Buffett shareholder letter {year}",
                    text=text,
                    url=url,
                ))
            except Exception:
                continue
        return docs
