"""Scrape Larry Summers columns + Brookings papers.

Project Syndicate gives us a clean RSS feed; Brookings has no clean RSS
for individual contributors so we hand-curate a known URL list (extend
manually as new pieces are published).
"""
from __future__ import annotations

from datetime import datetime, UTC
from email.utils import parsedate_to_datetime

import httpx
from bs4 import BeautifulSoup

import feedparser

from castelino.agents.personas.corpus import CorpusDoc
from castelino.agents.personas.scrapers.base import PersonaScraper
from castelino.agents.personas.sonar_fetcher import fetch_persona_via_sonar


# Curated list of Brookings articles authored by Summers. Add to this list
# manually as new pieces are published; v2 could auto-discover via the
# Brookings author search.
BROOKINGS_KNOWN_URLS: list[str] = [
    # Examples — replace with real URLs as discovered.
    # "https://www.brookings.edu/articles/the-future-of-stagnation/",
]


class SummersScraper(PersonaScraper):
    persona_id = "summers"
    # Project Syndicate global feed; filter by author name.
    FEED_URL = "https://www.project-syndicate.org/rss"
    AUTHOR_MATCH = "summers"

    def _fetch_feed(self, url: str) -> str:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.text

    async def _fetch_article(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text

    def _parse_article_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        article = soup.find("article") or soup.find("div", class_="content") or soup
        return article.get_text(" ", strip=True)

    def _parse_pubdate(self, raw: str) -> datetime:
        try:
            return parsedate_to_datetime(raw).astimezone(UTC)
        except Exception:
            return datetime.now(UTC)

    def _brookings_urls(self) -> list[str]:
        return list(BROOKINGS_KNOWN_URLS)

    async def fetch(self) -> list[CorpusDoc]:
        try:
            feed = feedparser.parse(self._fetch_feed(self.FEED_URL))
        except Exception:
            feed = feedparser.parse("")  # falls through to Sonar
        docs: list[CorpusDoc] = []
        # Project Syndicate columns — global feed, filter by author
        for entry in feed.entries:
            try:
                author = (entry.get("author") or "").lower()
                if self.AUTHOR_MATCH not in author:
                    continue
                url = entry.link
                date = self._parse_pubdate(entry.get("published", ""))
                html_summary = entry.get("summary", "") or ""
                text = self._parse_article_html(html_summary)
                if len(text) < 50:
                    continue
                docs.append(CorpusDoc(
                    source=url.rsplit("/", 1)[-1] or url,
                    date=date, title=entry.title, text=text, url=url,
                ))
            except Exception:
                continue
        # Brookings curated URLs
        for url in self._brookings_urls():
            try:
                html = await self._fetch_article(url)
                text = self._parse_article_html(html)
                if not text.strip():
                    continue
                docs.append(CorpusDoc(
                    source="brookings_" + url.rsplit("/", 1)[-1],
                    date=datetime.now(UTC),
                    title=url.rsplit("/", 1)[-1].replace("-", " ").title(),
                    text=text, url=url,
                ))
            except Exception:
                continue

        if len(docs) < 3:
            docs.extend(fetch_persona_via_sonar(
                persona_id=self.persona_id, persona_name="Lawrence H. Summers",
            ))
        return docs
