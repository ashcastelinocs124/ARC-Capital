"""GET /x_feed: the newest posts on @AshleynCas46131 (no replies or reposts) for Home's "Latest on X"
row and About's "On X" feed, newest first.

X's API bills each post it returns (about $0.005), so data/x_feed.json keeps the last KEEP posts and
asks X only for posts newer than its newest (since_id), at most every TTL_S: an export with nothing
new costs nothing. Without the X user keys (only Fly has them) it serves that file as it is.
"""

from __future__ import annotations

import html
import json
import time

import httpx
from fastapi import APIRouter

from castelino import x_post
from castelino.agents.update.fsio import atomic_write_text
from castelino.config import get_settings

router = APIRouter()

HANDLE = "AshleynCas46131"
USER_ID = "1702425364474044416"  # GET /2/users/me with Fly's X keys, 2026-10-20
TIMELINE = f"https://api.x.com/2/users/{USER_ID}/tweets"
KEEP = 10  # About shows 5, then "Show 5 more"
TTL_S = 600
# ponytail: a post deleted on X stays here until KEEP newer ones push it out


def _path():
    return get_settings().root / "data" / "x_feed.json"


def parse(reply: dict) -> list[dict]:
    """X's timeline reply -> posts: id, time, text, the first image and the link. A photo's t.co link
    is dropped (the image shows it) and any other is written as its display text; emoji go, as on
    every ARC post."""
    media = {m.get("media_key"): m for m in reply.get("includes", {}).get("media", [])}
    out = []
    for t in reply.get("data", []):
        if not str(t.get("id", "")).isdigit() or t.get("in_reply_to_user_id"):
            continue  # the id becomes a link; exclude=replies still sends a thread's own replies
        text = t.get("text", "")
        for u in t.get("entities", {}).get("urls", []):
            if u.get("media_key"):  # with the space before it
                text = text.replace(f" {u.get('url')}", "").replace(u.get("url", ""), "")
            else:
                text = text.replace(u.get("url", ""), u.get("display_url", ""))
        imgs = [media.get(k, {}) for k in t.get("attachments", {}).get("media_keys", [])]
        img = next((m.get("url") or m.get("preview_image_url") for m in imgs if m), None)
        out.append(
            {
                "id": t["id"],
                "at": t.get("created_at", ""),
                "text": x_post.no_emoji(html.unescape(text)).strip(),
                "image": img if img and img.startswith("https://pbs.twimg.com/") else None,
                "url": f"https://x.com/{HANDLE}/status/{t['id']}",
            }
        )
    return out


def refresh(now: float | None = None, get=httpx.get) -> list[dict]:
    p = _path()
    cache = json.loads(p.read_text()) if p.exists() else {"posts": [], "checked": 0}
    now = time.time() if now is None else now
    if not x_post.can_post() or now - cache.get("checked", 0) < TTL_S:
        return cache["posts"]
    params = {
        "max_results": str(KEEP),
        "exclude": "replies,retweets",
        "tweet.fields": "created_at,attachments,entities,in_reply_to_user_id",
        "expansions": "attachments.media_keys",
        "media.fields": "url,preview_image_url",
    }
    if cache["posts"]:
        params["since_id"] = cache["posts"][0]["id"]
    auth = x_post._auth_header("GET", TIMELINE, params)
    r = get(TIMELINE, params=params, headers={"Authorization": auth}, timeout=20)
    r.raise_for_status()
    posts = (parse(r.json()) + cache["posts"])[:KEEP]
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, json.dumps({"posts": posts, "checked": now}))
    return posts


@router.get("/x_feed")
def x_feed():
    try:
        return refresh()
    except (httpx.HTTPError, ValueError, KeyError):  # e.g. 402 when the X credits run out
        p = _path()
        return json.loads(p.read_text())["posts"] if p.exists() else []
