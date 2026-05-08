"""Scrape Mohamed El-Erian columns from Project Syndicate.

Same structural pattern as KrugmanScraper — RSS feed → article page →
BeautifulSoup-strip to plain text. v2 can layer in Bloomberg/FT but
those are paywalled so leave for later.
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


class ElErianScraper(PersonaScraper):
    persona_id = "el_erian"
    # Project Syndicate global feed; filter by author name.
    FEED_URL = "https://www.project-syndicate.org/rss"
    AUTHOR_MATCH = "el-erian"

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

    async def fetch(self) -> list[CorpusDoc]:
        try:
            feed = feedparser.parse(self._fetch_feed(self.FEED_URL))
        except Exception:
            feed = feedparser.parse("")
        docs: list[CorpusDoc] = []
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

        if len(docs) < 3:
            docs.extend(fetch_persona_via_sonar(
                persona_id=self.persona_id, persona_name="Mohamed A. El-Erian",
            ))
        return docs
