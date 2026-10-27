"""GET /x_feed: the newest posts on @AshleynCas46131 (no replies to others, no reposts) for Home's
"Latest on X" row and About's "On X" feed, newest first. Each post carries the rest of its own thread
(the analysis and chart posts) and the ARC report on Substack the thread links, if any.

X's API bills each post it returns (about $0.005), so data/x_feed.json keeps the last KEEP posts and
asks X only for posts newer than its newest (since_id), at most every TTL_S: an export with nothing
new costs nothing. Without the X user keys (only Fly has them) it serves that file as it is.

Only market posts show (user rule, 2026-10-27, after a football post led Home's strip): one Decisions API
call per post, kept with it as `market`, so each post is asked once.
"""

from __future__ import annotations

import html
import itertools
import json
import time

import httpx
from fastapi import APIRouter

from castelino import benchmark, x_post
from castelino.agents.trade import llm
from castelino.agents.trade.decide import predicates
from castelino.agents.update.fsio import atomic_write_text
from castelino.config import get_settings

router = APIRouter()

HANDLE = "AshleynCas46131"
USER_ID = "1702425364474044416"  # GET /2/users/me with Fly's X keys, 2026-10-20
TIMELINE = f"https://api.x.com/2/users/{USER_ID}/tweets"
KEEP = 20  # top-level posts, each with its thread; Home and About show 6, then "Show more" for all
TTL_S = 600
PER_CALL = 50  # a thread's posts count too; since_id keeps each one billed once
REPORT_PREFIX = "https://archresearch.substack.com/p/"  # the only report link a card may carry
VERSION = 3  # 2: posts carry `thread` + `report`; 3: refetched once to fill KEEP = 20; an older file is rebuilt once
# ponytail: a post deleted on X stays here until KEEP newer ones push it out
QUESTION = {
    "market": (
        "The post is about markets, the economy, companies, investing, AI as an industry or ARC Research's "
        "work. Sports, personal life, small talk and jokes do not count."
    )
}
PROMPT = QUESTION["market"]  # shown on /admin → Agents


def _path():
    return get_settings().root / "data" / "x_feed.json"


def _post(t: dict, media: dict) -> dict:
    """One X post -> id, time, text, the first image, its link and any ARC report it links. A photo's
    t.co link is dropped (the image shows it), a Substack report's too (the card shows it), and any
    other is written as its display text; emoji go, as on every ARC post."""
    text, report = t.get("text", ""), None
    for u in t.get("entities", {}).get("urls", []):
        target = (u.get("expanded_url") or "").split("?")[0].split("#")[0]
        if u.get("media_key") or target.startswith(REPORT_PREFIX):  # with the space before it
            text = text.replace(f" {u.get('url')}", "").replace(u.get("url", ""), "")
            if not u.get("media_key") and report is None:
                slug = target.removeprefix(REPORT_PREFIX).strip("/").replace("-", " ")
                title = x_post.no_emoji(html.unescape(u.get("title") or "")).strip()
                report = {"url": target, "title": title or slug.capitalize()}
        else:
            text = text.replace(u.get("url", ""), u.get("display_url", ""))
    imgs = [media.get(k, {}) for k in t.get("attachments", {}).get("media_keys", [])]
    img = next((m.get("url") or m.get("preview_image_url") for m in imgs if m), None)
    return {
        "id": t["id"],
        "at": t.get("created_at", ""),
        "text": x_post.no_emoji(html.unescape(text)).strip(),
        "image": img if img and img.startswith("https://pbs.twimg.com/") else None,
        "url": f"https://x.com/{HANDLE}/status/{t['id']}",
        "report": report,
    }


def parse(reply: dict, cached: list[dict] | None = None) -> list[dict]:
    """X's timeline reply (+ the posts already kept) -> your top-level posts, newest first, each with
    the rest of its own thread (`thread`, in order: X Scout's 2/ 3/ 4/, Theme Charts' chart posts) and
    the ARC report any of them links (`report`). Replies to other people never show."""
    media = {m.get("media_key"): m for m in reply.get("includes", {}).get("media", [])}
    leads = {
        p["id"]: {**p, "thread": list(p.get("thread", [])), "report": p.get("report")}
        for p in cached or []
    }
    later: list[tuple[str, dict]] = []
    for t in reply.get("data", []):
        if not str(t.get("id", "")).isdigit():
            continue  # the id becomes a link
        to = t.get("in_reply_to_user_id")
        if to and to != USER_ID:
            continue  # a reply to someone else
        p = _post(t, media)
        if to:  # exclude=replies still sends a thread's own posts: keep them under their lead
            if (conv := str(t.get("conversation_id", ""))) and conv != p["id"]:
                later.append((conv, p))
            continue
        leads.setdefault(p["id"], {**p, "thread": []})
    for conv, p in later:
        lead = leads.get(conv)
        if lead is None or any(x["id"] == p["id"] for x in lead["thread"]):
            continue  # its lead is older than the feed keeps, or it's already here
        lead["thread"].append({k: p[k] for k in ("id", "text", "image", "url")})
        lead["report"] = lead["report"] or p["report"]
    for lead in leads.values():
        lead["thread"].sort(key=lambda x: int(x["id"]))
    return sorted(leads.values(), key=lambda p: int(p["id"]), reverse=True)


def _market(p: dict) -> bool:
    """Whether the feed shows a post: asked once (a probability of 0.5 or more), the answer kept with it."""
    if "market" not in p:
        try:
            ask = predicates(p.get("text", ""), QUESTION, llm.Meter(), agent="x_feed_filter")
            p["market"] = ask["market"] >= 0.5
        except Exception:  # noqa: BLE001 - the fallback failed too: show it, ask again next refresh
            return True
    return p["market"]


def refresh(now: float | None = None, get=httpx.get) -> list[dict]:
    p = _path()
    cache = json.loads(p.read_text()) if p.exists() else {"posts": [], "checked": 0}
    now = time.time() if now is None else now
    # a check time in the future (as on Fly, Oct 22-27) would freeze the feed for good
    if not x_post.can_post() or 0 <= now - cache.get("checked", 0) < TTL_S:
        return cache["posts"]
    params = {
        "max_results": str(PER_CALL),
        "exclude": "replies,retweets",
        "tweet.fields": "created_at,attachments,entities,in_reply_to_user_id,conversation_id",
        "expansions": "attachments.media_keys",
        "media.fields": "url,preview_image_url",
    }
    fresh = cache.get("v") == VERSION
    if fresh and cache.get("newest"):  # an older file never kept threads: fetch them once
        params["since_id"] = cache["newest"]
    auth = x_post._auth_header("GET", TIMELINE, params)
    r = get(TIMELINE, params=params, headers={"Authorization": auth}, timeout=20)
    r.raise_for_status()
    reply = r.json()
    benchmark.record_x("read", len(reply.get("data", [])))  # X bills each post it returns
    posts = parse(reply, cache["posts"] if fresh else None)
    if not fresh:  # keep older posts the refetch didn't reach
        seen = {x["id"] for x in posts}
        posts += [
            {"thread": [], "report": None, **x} for x in cache["posts"] if x["id"] not in seen
        ]
    posts = list(itertools.islice((x for x in posts if _market(x)), KEEP))  # asks only as needed
    ids = [str(t["id"]) for t in reply.get("data", []) if str(t.get("id", "")).isdigit()]
    newest = max([*ids, cache.get("newest") or "0"] if fresh else [*ids, "0"], key=int)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        p, json.dumps({"v": VERSION, "posts": posts, "checked": now, "newest": newest})
    )
    return posts


@router.get("/x_feed")
def x_feed():
    try:
        return refresh()
    except (httpx.HTTPError, ValueError, KeyError):  # e.g. 402 when the X credits run out
        p = _path()
        return json.loads(p.read_text())["posts"] if p.exists() else []
