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
_feed: tuple[float, str] = (0.0, "")
_archive: tuple[float, list] = (0.0, [])


# hand-made covers for any Substack post (videos, sections, daily notes), by post slug; files in frontend/public/thumbs/
THUMB_OVERRIDES = {
    "cheaper-frontier-models-efficient": "/thumbs/chinachip.jpg",
    "weekly-market-update-1": "/thumbs/weekly-market-update-1.jpg",
    "money-for-machines": "/thumbs/money-for-machines.jpg",
    "neolabs-and-neoclouds": "/thumbs/neolabs-and-neoclouds.jpg",
    "how-ai-has-become-a-capital-markets": "/thumbs/ai-capital-markets.jpg",
    "fed-pause-expectations-rose-even": "/thumbs/fed-pause-expectations.jpg",
    "hike-risk-oil-shocks-and-an-ai-reality": "/thumbs/hike-risk-oil-shocks.jpg",
    "overview-of-nvidias-open-agent-safety": "/thumbs/nvidia-openagent.jpg",
    "fed-officials-kept-another-hike-in": "/thumbs/fed-officials-another-hike.jpg",
    "september-inflation-accelerated-as": "/thumbs/inflation-heats-up.jpg",
}


def feed_xml() -> str:
    """The Substack RSS text, cached for an hour (also read by /daily_posts). Raises on a network error."""
    global _feed
    if time.time() - _feed[0] >= _TTL_S:
        r = httpx.get(FEED, timeout=20, follow_redirects=True)
        r.raise_for_status()
        _feed = (time.time(), r.text)
    return _feed[1]


def archive_json() -> list[dict]:
    """Substack's post archive (covers, durations, sections), cached for an hour. Raises on an error."""
    global _archive
    if time.time() - _archive[0] >= _TTL_S:
        r = httpx.get(ARCHIVE, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise ValueError("unexpected archive reply")
        _archive = (time.time(), data)
    return _archive[1]


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
        # A video embedded in a newsletter post has no cover; its first frame sits at a fixed S3 path.
        upload = re.search(r"mediaUploadId&quot;:&quot;([0-9a-f-]{36})", body)
        if not thumb and upload and post.get("id"):
            thumb = f"https://substack-video.s3.amazonaws.com/video_upload/post/{post['id']}/{upload.group(1)}/transcoded-00001.png"
        thumb = THUMB_OVERRIDES.get(link.rsplit("/", 1)[-1], thumb)
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
        xml = feed_xml()
        try:
            archive = archive_json()
        except (httpx.HTTPError, ValueError):
            archive = []  # thumbnails and durations are optional
        _cache = (time.time(), parse_videos(xml, archive))
    except (httpx.HTTPError, ET.ParseError, ValueError):
        return _cache[
            1
        ]  # ponytail: stale or empty on a feed hiccup; the page shows its empty state
    return _cache[1]
