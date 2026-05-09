"""Scrape federalreserve.gov speeches by speaker.

Layout (as of 2026):
- Index: federalreserve.gov/newsevents/speech/<year>-speeches.htm
- Detail: federalreserve.gov/newsevents/speech/<speaker>YYYYMMDDa.htm
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class SpeechIndexItem:
    url: str
    speaker: str
    date: datetime
    title: str


@dataclass(frozen=True)
class ParsedSpeech:
    speaker: str
    date: datetime
    venue: str
    title: str
    text: str
    url: str


_DATE_RX = re.compile(r"(\w+ \d+, \d{4})")


def parse_speech_page(html: str, *, url: str) -> ParsedSpeech:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.find("h3", class_="title") or soup.find("h1") or soup.title
    title = title_el.get_text(strip=True) if title_el else ""
    speaker_el = soup.find("p", class_="speaker") or soup.find(class_="byline")
    speaker_txt = speaker_el.get_text(strip=True) if speaker_el else ""
    date_blob = soup.find("p", class_="article__time") or soup.find(class_="article-date")
    date_txt = date_blob.get_text(strip=True) if date_blob else ""
    m = _DATE_RX.search(date_txt) or _DATE_RX.search(html[:5000])
    date = (
        datetime.strptime(m.group(1), "%B %d, %Y").replace(tzinfo=UTC)
        if m
        else datetime.now(UTC)
    )
    venue_el = soup.find("p", class_="location") or soup.find(class_="article__location")
    venue = venue_el.get_text(strip=True) if venue_el else ""
    body = soup.find("div", id="article") or soup.find(
        "div", class_="col-xs-12 col-sm-8 col-md-8"
    )
    text = body.get_text(" ", strip=True) if body else soup.get_text(" ", strip=True)
    return ParsedSpeech(
        speaker=speaker_txt,
        date=date,
        venue=venue,
        title=title,
        text=text,
        url=url,
    )


def parse_speech_index(html: str, *, base_url: str) -> list[SpeechIndexItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[SpeechIndexItem] = []
    for row in soup.select("div.row.eventlist__item, .panel--default tr, .speech-item"):
        link = row.find("a", href=True)
        if not link:
            continue
        url = urljoin(base_url, link["href"])
        title = link.get_text(strip=True)
        speaker_el = row.find(class_="speaker")
        speaker = speaker_el.get_text(strip=True) if speaker_el else ""
        m = _DATE_RX.search(row.get_text(" ", strip=True))
        date = (
            datetime.strptime(m.group(1), "%B %d, %Y").replace(tzinfo=UTC)
            if m
            else datetime.now(UTC)
        )
        items.append(SpeechIndexItem(url=url, speaker=speaker, date=date, title=title))
    return items


INDEX_URL = "https://www.federalreserve.gov/newsevents/speech/{year}-speeches.htm"


async def fetch_speeches_for_speaker(
    *,
    speaker_match: str,
    year: int,
    client: httpx.AsyncClient,
) -> list[ParsedSpeech]:
    idx_html = (await client.get(INDEX_URL.format(year=year))).text
    base = str(client.base_url) or "https://www.federalreserve.gov"
    items = [
        i
        for i in parse_speech_index(idx_html, base_url=base)
        if speaker_match.lower() in i.speaker.lower()
    ]
    out: list[ParsedSpeech] = []
    for item in items:
        html = (await client.get(item.url)).text
        out.append(parse_speech_page(html, url=item.url))
    return out
