"""Posts by the tracked accounts from the X API v2 recent search (last 7 days only).

The query names the authors (from:handle) and the provider keywords, so every post comes
straight from X with its real text and author: no model in the loop.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

URL = "https://api.x.com/2/tweets/search/recent"
NY = ZoneInfo("America/New_York")
MAX_QUERY = 512  # X's query length limit on the self-serve tiers
DAY_CAP = 1000  # posts read per day at most, so the monthly read cap can't be overrun
SUFFIX = " -is:retweet"


def has_key() -> bool:
    return bool(os.environ.get("X_BEARER_TOKEN", "").strip())


def _kw(k: str) -> str:
    return f'"{k}"' if " " in k else k


def build_queries(handles: list[str], families: dict[str, list[str]]) -> list[str]:
    """Pack `(from:a OR from:b …) (kw OR kw …) -is:retweet` queries under MAX_QUERY."""
    kws = "(" + " OR ".join(_kw(k) for ks in families.values() for k in ks) + ")"
    fixed = len(kws) + len(SUFFIX) + 3  # "()" around authors + a space
    queries, cur = [], []
    for h in handles:
        trial = cur + [f"from:{h}"]
        if cur and fixed + len(" OR ".join(trial)) > MAX_QUERY:
            queries.append(cur)
            trial = [f"from:{h}"]
        cur = trial
    if cur:
        queries.append(cur)
    return [f"({' OR '.join(q)}) {kws}{SUFFIX}" for q in queries]


def window(day: date, now: datetime) -> tuple[str, str]:
    """The New York calendar day in UTC; the end is clamped 30 s before now (X's rule)."""
    start = datetime.combine(day, time.min, NY).astimezone(UTC)
    end = min(start + timedelta(days=1), now.astimezone(UTC) - timedelta(seconds=30))
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), end.strftime(fmt)


def _get(params: dict) -> dict:
    token = os.environ["X_BEARER_TOKEN"].strip()
    r = httpx.get(URL, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"x api: HTTP {r.status_code} {r.text[:120]}")
    return r.json()


def search(
    query: str, start: str, end: str, get=_get, cap: int = DAY_CAP, max_results: int = 100
) -> list[dict]:
    posts: list[dict] = []
    params = {
        "query": query,
        "start_time": start,
        "end_time": end,
        "max_results": max(10, min(100, max_results)),  # X allows 10-100 per page
        "tweet.fields": "created_at,author_id,note_tweet",
        "expansions": "author_id",
        "user.fields": "username",
    }
    while True:
        page = get(dict(params))
        users = {u["id"]: u["username"].lower() for u in page.get("includes", {}).get("users", [])}
        for t in page.get("data", []):
            author = users.get(t["author_id"])
            if not author:
                continue
            text = (t.get("note_tweet") or {}).get("text") or t[
                "text"
            ]  # long posts arrive truncated
            posts.append(
                {"url": f"https://x.com/{author}/status/{t['id']}", "author": author, "text": text}
            )
        token = page.get("meta", {}).get("next_token")
        if not token or len(posts) >= cap:
            return posts
        params["next_token"] = token


def fetch_day(handles: list[str], families: dict, day: date, now: datetime, get=_get) -> list[dict]:
    start, end = window(day, now)
    posts: list[dict] = []
    for q in build_queries(handles, families):
        posts += search(q, start, end, get=get, cap=DAY_CAP - len(posts))
        if len(posts) >= DAY_CAP:
            break
    return posts
