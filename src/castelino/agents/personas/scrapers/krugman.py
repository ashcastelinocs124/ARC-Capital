"""Scrape Paul Krugman columns from Project Syndicate.

Project Syndicate publishes Krugman's columns in a public RSS feed at
https://www.project-syndicate.org/columnist/paul-krugman/feed. Each
entry has a link to the full article page, which we fetch and strip
to plain text via BeautifulSoup.
"""
from __future__ import annotations

from datetime import datetime, UTC
from email.utils import parsedate_to_datetime

import httpx
from bs4 import BeautifulSoup

import feedparser

from castelino.agents.personas.corpus import CorpusDoc
from castelino.agents.personas.scrapers.base import PersonaScraper


class KrugmanScraper(PersonaScraper):
    persona_id = "krugman"
    FEED_URL = "https://www.project-syndicate.org/columnist/paul-krugman/feed"

    def _fetch_feed(self, url: str) -> str:
        # Synchronous because feedparser is sync; small payload.
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
        feed_xml = self._fetch_feed(self.FEED_URL)
        feed = feedparser.parse(feed_xml)
        docs: list[CorpusDoc] = []
        for entry in feed.entries:
            try:
                url = entry.link
                title = entry.title
                date = self._parse_pubdate(entry.get("published", ""))
                html = await self._fetch_article(url)
                text = self._parse_article_html(html)
                if not text.strip():
                    continue
                docs.append(CorpusDoc(
                    source=url.rsplit("/", 1)[-1] or url,
                    date=date, title=title, text=text, url=url,
                ))
            except Exception:
                continue
        return docs
