"""Scrape Ray Dalio publications from Bridgewater Associates.

LinkedIn is auth-gated and not programmatically scrapable. Bridgewater
publishes research at https://www.bridgewater.com/research-and-insights/ —
we hand-curate a list of known article URLs and fetch each page's text.
Add to BRIDGEWATER_KNOWN_URLS manually as new pieces are published.

Sonar fallback fires when the curated list yields < 3 docs.
"""
from __future__ import annotations

from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from castelino.agents.personas.corpus import CorpusDoc
from castelino.agents.personas.scrapers.base import PersonaScraper
from castelino.agents.personas.sonar_fetcher import fetch_persona_via_sonar


# Curated Bridgewater publication URLs. Add here as new pieces are published.
# v2 could auto-discover via the Bridgewater research search page.
BRIDGEWATER_KNOWN_URLS: list[str] = [
    # Examples — replace with real URLs as discovered:
    # "https://www.bridgewater.com/research-and-insights/the-changing-world-order",
    # "https://www.bridgewater.com/research-and-insights/principles-for-navigating-big-debt-crises",
]


class DalioScraper(PersonaScraper):
    persona_id = "dalio"

    def _known_urls(self) -> list[str]:
        return list(BRIDGEWATER_KNOWN_URLS)

    async def _fetch_article(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text

    def _parse_article_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        article = soup.find("article") or soup.find("div", class_="content") or soup
        return article.get_text(" ", strip=True)

    async def fetch(self) -> list[CorpusDoc]:
        docs: list[CorpusDoc] = []
        for url in self._known_urls():
            try:
                html = await self._fetch_article(url)
                text = self._parse_article_html(html)
                if len(text) < 50:
                    continue
                slug = url.rstrip("/").rsplit("/", 1)[-1] or url
                docs.append(CorpusDoc(
                    source=f"bridgewater_{slug}",
                    date=datetime.now(UTC),
                    title=slug.replace("-", " ").title(),
                    text=text,
                    url=url,
                ))
            except Exception:
                continue

        if len(docs) < 3:
            docs.extend(fetch_persona_via_sonar(
                persona_id=self.persona_id, persona_name="Ray Dalio",
            ))
        return docs
