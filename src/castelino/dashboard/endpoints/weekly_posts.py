"""GET /weekly_posts: the published ARC Weekly Deep Dive posts on Substack (week, title, takeaways, cover, link).

Read from the archive API, not the RSS feed: the feed can lag a new post by days.
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx
from fastapi import APIRouter

from castelino.dashboard.endpoints.videos import POST_PREFIX, THUMB_OVERRIDES, archive_json

router = APIRouter()

# Substack's subtitle is "ARC Weekly Deep Dive · Oct 5–Oct 9, 2026" (set by castelino/substack_weekly.py).
_SUBTITLE = re.compile(
    r"^ARC Weekly Deep Dive\s*\S*\s*(\w{3} \d{1,2})\s*[–-]\s*(\w{3} \d{1,2}), (\d{4})"
)


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def _takeaways(body: str) -> list[str]:
    """The bold lead of each bullet in the first list (the week at a glance), else the whole bullet."""
    ul = re.search(r"<ul>(.*?)</ul>", body, re.S)
    if not ul:
        return []
    out = []
    for li in re.findall(r"<li>(.*?)</li>", ul.group(1), re.S):
        lead = re.search(r"<strong>(.*?)</strong>", li, re.S)
        out.append(_strip(lead.group(1) if lead else li))
    return [t for t in out if t]


def parse_weekly_posts(
    archive: list[dict], overrides: dict[str, str] = THUMB_OVERRIDES
) -> list[dict]:
    out = []
    for p in archive:
        m = _SUBTITLE.match((p.get("subtitle") or "").strip())
        url = p.get("canonical_url") or ""
        if not m or not url.startswith(POST_PREFIX):  # the link is rendered as an href
            continue
        start = datetime.strptime(f"{m.group(1)} {m.group(3)}", "%b %d %Y").date()
        end = datetime.strptime(f"{m.group(2)} {m.group(3)}", "%b %d %Y").date()
        if start > end:  # "Dec 29–Jan 2, 2026": the year is the end's
            start = start.replace(year=start.year - 1)
        iso = start.isocalendar()
        cover = p.get("cover_image") or ""
        out.append(
            {
                "week": f"{iso[0]}-W{iso[1]:02d}",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "title": (p.get("title") or "").strip(),
                "takeaways": _takeaways(p.get("body_html") or ""),
                "image": overrides.get(
                    p.get("slug") or "", cover if cover.startswith("https://") else None
                ),
                "url": url,
            }
        )
    return sorted(out, key=lambda p: p["start"], reverse=True)


def _with_body(p: dict) -> dict:
    """The archive list leaves body_html empty; fetch the post itself for a weekly (a few posts, so no cache)."""
    if p.get("body_html") or not _SUBTITLE.match((p.get("subtitle") or "").strip()):
        return p
    try:
        r = httpx.get(f"https://archresearch.substack.com/api/v1/posts/{p.get('slug')}", timeout=20)
        r.raise_for_status()
        return {**p, "body_html": r.json().get("body_html") or ""}
    except (httpx.HTTPError, ValueError):
        return p  # the card just shows no takeaways


@router.get("/weekly_posts")
def weekly_posts():
    try:
        return parse_weekly_posts([_with_body(p) for p in archive_json()])
    except (httpx.HTTPError, ValueError):
        return []  # ponytail: the page shows its empty state on an archive hiccup
