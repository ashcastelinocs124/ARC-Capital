"""GET /videos: the ARC Research Substack's video posts (title, link, date, thumbnail), read from its RSS feed."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx
from fastapi import APIRouter

router = APIRouter()

FEED = "https://archresearch.substack.com/feed"
ARCHIVE = "https://archresearch.substack.com/api/v1/archive?sort=new&limit=50"  # has video covers and durations
POST_PREFIX = "https://archresearch.substack.com/p/"
_CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
_TTL_S = 3600
_cache: tuple[float, list[dict]] = (0.0, [])


def parse_videos(xml: str, archive: list[dict] | None = None) -> list[dict]:
    """A post counts as a video when it has a native video embed, a YouTube/Vimeo iframe or an
    audio enclosure (Substack attaches the soundtrack of an uploaded video as audio/mpeg)."""
    meta = {p.get("slug"): p for p in archive or []}
    out = []
    for item in ET.fromstring(xml).iter("item"):
        link = (item.findtext("link") or "").strip()
        body = item.findtext(_CONTENT) or ""
        enc = item.find("enclosure")
        is_video = (
            "native-video-embed" in body
            or re.search(r"youtube\.com/embed|player\.vimeo\.com", body)
            or (enc is not None and (enc.get("type") or "").startswith("audio/"))
        )
        if not is_video or not link.startswith(POST_PREFIX):  # the link is rendered as an href
            continue
        post = meta.get(link.rsplit("/", 1)[-1], {})
        cover = post.get("cover_image") or ""
        thumb = cover if cover.startswith("https://substack-video.s3.amazonaws.com/") else None
        date = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        out.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "url": link,
                "date": date,
                "summary": (item.findtext("description") or "").strip(),
                "thumbnail": thumb,
                "duration": round(post["podcast_duration"])
                if post.get("podcast_duration")
                else None,
            }
        )
    return out


@router.get("/videos")
def videos():
    global _cache
    if time.time() - _cache[0] < _TTL_S:
        return _cache[1]
    try:
        r = httpx.get(FEED, timeout=20, follow_redirects=True)
        r.raise_for_status()
        try:
            archive = httpx.get(ARCHIVE, timeout=20).json()
        except (httpx.HTTPError, ValueError):
            archive = []  # thumbnails and durations are optional
        _cache = (time.time(), parse_videos(r.text, archive))
    except (httpx.HTTPError, ET.ParseError, ValueError):
        return _cache[
            1
        ]  # ponytail: stale or empty on a feed hiccup; the page shows its empty state
    return _cache[1]
