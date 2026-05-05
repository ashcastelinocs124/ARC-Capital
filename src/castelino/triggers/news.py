"""News RSS ingestion — pulls a small set of macro feeds and de-duplicates."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import feedparser

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
