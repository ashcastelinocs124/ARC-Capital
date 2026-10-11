"""GET /daily_posts: the published ARC Daily Note posts on Substack (date, headline, takeaways, image, link)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx
from fastapi import APIRouter

from castelino.dashboard.endpoints.videos import _CONTENT, POST_PREFIX, THUMB_OVERRIDES, feed_xml

router = APIRouter()

# Substack's subtitle is "ARC Daily Note · Thursday, October 8, 2026" (set by castelino/substack.py).
_SUBTITLE = re.compile(r"^ARC Daily Note\s*\S*\s*\w+, (\w+ \d{1,2}, \d{4})")


def parse_daily_posts(xml: str) -> list[dict]:
    out = []
    for item in ET.fromstring(xml).iter("item"):
        m = _SUBTITLE.match((item.findtext("description") or "").strip())
        link = (item.findtext("link") or "").strip()
        if not m or not link.startswith(POST_PREFIX):  # the link is rendered as an href
            continue
        body = item.findtext(_CONTENT) or ""
        ul = re.search(r"<ul>(.*?)</ul>", body, re.S)  # the first bullet list is the takeaways
        takeaways = (
            [
                re.sub(r"<[^>]+>", "", li).strip()
                for li in re.findall(r"<li>(.*?)</li>", ul.group(1), re.S)
            ]
            if ul
            else []
        )
        enc = item.find("enclosure")
        image = (
            enc.get("url")
            if enc is not None and (enc.get("type") or "").startswith("image/")
            else None
        )
        out.append(
            {
                "date": datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat(),
                "title": (item.findtext("title") or "").strip(),
                "takeaways": takeaways,
                "image": THUMB_OVERRIDES.get(
                    link.rsplit("/", 1)[-1],
                    image if image and image.startswith("https://") else None,
                ),
                "url": link,
            }
        )
    return sorted(out, key=lambda p: p["date"], reverse=True)


@router.get("/daily_posts")
def daily_posts():
    try:
        return parse_daily_posts(feed_xml())
    except (httpx.HTTPError, ET.ParseError, ValueError):
        return []  # ponytail: the page shows its empty state on a feed hiccup
