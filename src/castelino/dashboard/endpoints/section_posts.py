"""GET /section_posts: posts in the Substack sections shown on Daily Update (AI Update, Special Topics)."""

from __future__ import annotations

import httpx
from fastapi import APIRouter

from castelino.dashboard.endpoints.videos import POST_PREFIX, THUMB_OVERRIDES, archive_json

router = APIRouter()

# Substack section slug -> shown on the site (the order is the page order).
SECTIONS = {"artificial-intelligence-update": "AI Update", "special-topics": "Special Topics"}


def parse_section_posts(archive: list[dict]) -> list[dict]:
    out = []
    for p in archive:
        slug = p.get("section_slug")
        url = p.get("canonical_url") or ""
        if slug not in SECTIONS or not url.startswith(
            POST_PREFIX
        ):  # the url is rendered as an href
            continue
        cover = p.get("cover_image") or ""
        out.append(
            {
                "section": slug,
                "title": (p.get("title") or "").strip(),
                "url": url,
                "date": (p.get("post_date") or "")[:10],
                "summary": (p.get("description") or p.get("subtitle") or "").strip(),
                "thumbnail": THUMB_OVERRIDES.get(
                    url.rsplit("/", 1)[-1], cover if cover.startswith("https://") else None
                ),
                "duration": round(p["podcast_duration"]) if p.get("podcast_duration") else None,
                "video": bool(p.get("videoUpload") or p.get("type") == "podcast"),
            }
        )
    return sorted(out, key=lambda p: p["date"], reverse=True)


@router.get("/section_posts")
def section_posts():
    try:
        return parse_section_posts(archive_json())
    except (httpx.HTTPError, ValueError):
        return []  # ponytail: the page shows its empty state on an archive hiccup
