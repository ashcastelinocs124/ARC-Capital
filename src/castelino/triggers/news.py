"""News RSS ingestion — pulls a small set of macro feeds and de-duplicates.

Includes Sonar-based deep-read enrichment for significant headlines.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import feedparser
from openai import OpenAI

from castelino.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsHeadline:
    id: str            # stable hash of (link, title)
    title: str
    summary: str
    link: str
    source: str
    published: datetime
    deep_summary: str = ""  # Sonar-enriched summary (~200 words)


def _news_cache_path() -> Path:
    return get_settings().resolved_paths.data / "news_cache.json"


def _load_seen() -> dict[str, str]:
    p = _news_cache_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _save_seen(seen: dict[str, str]) -> None:
    p = _news_cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(seen, indent=2))


def fetch_recent(max_per_feed: int = 20, dedupe: bool = True) -> list[NewsHeadline]:
    """Pull every configured RSS feed; return deduplicated NewsHeadlines."""
    cfg = get_settings()
    seen = _load_seen() if dedupe else {}
    out: list[NewsHeadline] = []

    for url in cfg.triggers.rss_feeds:
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            log.warning("RSS fetch failed for %s: %s", url, e)
            continue
        source_name = feed.feed.get("title", url)
        for entry in feed.entries[:max_per_feed]:
            link = entry.get("link", "")
            title = entry.get("title", "").strip()
            if not title:
                continue
            ident = hashlib.sha1(f"{link}|{title}".encode()).hexdigest()
            if ident in seen:
                continue
            published = _parse_published(entry)
            out.append(
                NewsHeadline(
                    id=ident,
                    title=title,
                    summary=entry.get("summary", "")[:500],
                    link=link,
                    source=source_name,
                    published=published,
                )
            )
            seen[ident] = published.isoformat()

    if dedupe:
        # Drop seen entries older than 7d to keep the cache small.
        cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        seen = {k: v for k, v in seen.items() if v >= cutoff}
        _save_seen(seen)
    return sorted(out, key=lambda h: h.published, reverse=True)


def _parse_published(entry) -> datetime:
    """Robust published-time extraction — RSS feeds disagree about field names."""
    for key in ("published_parsed", "updated_parsed"):
        v = entry.get(key)
        if v:
            try:
                return datetime(*v[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                pass
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Sonar deep-read enrichment
# ---------------------------------------------------------------------------

_DEEP_READ_PROMPT = """\
Summarize this news event in 150-200 words, focusing on:
- What happened and why it matters for macro markets
- Immediate implications for rates, FX, equities, commodities
- Any forward-looking catalysts or risks

News headline: "{title}"
Source: {source}

Return ONLY the summary paragraph, no headers or bullet points.\
"""


def _article_cache_dir() -> Path:
    return get_settings().resolved_paths.cache / "sonar_articles"


def _read_article_cache(headline_id: str) -> str | None:
    p = _article_cache_dir() / f"{headline_id}.txt"
    if not p.exists():
        return None
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
    if (datetime.now(UTC) - mtime) > timedelta(hours=24):
        return None
    return p.read_text()


def _write_article_cache(headline_id: str, text: str) -> None:
    d = _article_cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{headline_id}.txt").write_text(text)


def _sonar_deep_read(headline: NewsHeadline) -> str:
    """Call Sonar for a single headline. Returns enriched summary or RSS fallback."""
    cached = _read_article_cache(headline.id)
    if cached:
        return cached

    cfg = get_settings()
    api_key = cfg.perplexity_api_key
    if not api_key:
        return headline.summary

    prompt = _DEEP_READ_PROMPT.format(title=headline.title, source=headline.source)
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
        resp = client.chat.completions.create(
            model=cfg.sonar.model,
            messages=[
                {"role": "system", "content": "You are a concise financial news analyst. Summarize the event factually."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text:
            _write_article_cache(headline.id, text)
            return text
    except Exception as e:
        log.warning("Sonar deep-read failed for %r: %s", headline.title, e)

    return headline.summary


def enrich_significant_headlines(headlines: list[NewsHeadline]) -> list[NewsHeadline]:
    """Enrich headlines with Sonar deep-reads. Only call on post-threshold headlines."""
    cfg = get_settings()
    if not cfg.perplexity_api_key:
        log.debug("PERPLEXITY_API_KEY not set — skipping headline enrichment")
        return headlines

    enriched: list[NewsHeadline] = []
    for h in headlines:
        deep = _sonar_deep_read(h)
        enriched.append(replace(h, deep_summary=deep))
    return enriched
