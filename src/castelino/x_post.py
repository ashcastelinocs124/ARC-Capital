"""Post a published Substack post to X: drafts, length check, OAuth 1.0a signing, the post chain.

Posting needs the account's user tokens (X developer portal → app → User authentication: Read and
write): X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET. X_BEARER_TOKEN (AI Model
Sentiment) is app-only and read-only, so it can't post. Used by the admin X posts tab.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from urllib.parse import quote

import httpx

TWEETS = "https://api.x.com/2/tweets"
LIMIT = 280
_URL = re.compile(r"https?://\S+")
KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")


def can_post() -> bool:
    return all(os.getenv(k) for k in KEYS)


def xlen(text: str) -> int:
    """X's weighted length: a link counts 23, most Latin text 1 per character, emoji and CJK 2."""
    text = _URL.sub("x" * 23, text)
    return sum(1 if ord(c) <= 4351 or 8192 <= ord(c) <= 8247 else 2 for c in text)


def drafts(kind: str, title: str, takeaways: list[str], url: str) -> list[str]:
    """A thread for both kinds: the title 🧵, one post per takeaway (≤5), then the link."""
    end = (
        "Full note on Substack"
        if kind == "daily"
        else "The full deep dive, with charts and sources"
    )
    return [
        f"{title} 🧵",
        *(f"{i}/ {t}" for i, t in enumerate(takeaways[:5], 1)),
        f"{end} → {url}",
    ]


def _enc(s: str) -> str:
    return quote(s, safe="~-._")


def signature(
    method: str, url: str, params: dict[str, str], consumer_secret: str, token_secret: str
) -> str:
    base = "&".join(
        [
            method.upper(),
            _enc(url),
            _enc("&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(params.items()))),
        ]
    )
    key = f"{_enc(consumer_secret)}&{_enc(token_secret)}"
    return base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()


def _auth_header(method: str, url: str) -> str:
    oauth = {
        "oauth_consumer_key": os.environ["X_API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": os.environ["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    # a JSON body is not part of the OAuth 1.0a signature
    oauth["oauth_signature"] = signature(
        method, url, oauth, os.environ["X_API_SECRET"], os.environ["X_ACCESS_SECRET"]
    )
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))


def post(text: str, reply_to: str | None = None) -> str:
    """One post; returns its id. Raises with X's message on failure."""
    body: dict = {"text": text}
    if reply_to:
        body["reply"] = {"in_reply_to_tweet_id": reply_to}
    r = httpx.post(
        TWEETS, json=body, headers={"Authorization": _auth_header("POST", TWEETS)}, timeout=30
    )
    if r.status_code >= 400:
        raise RuntimeError(f"X said {r.status_code}: {r.text[:300]}")
    return r.json()["data"]["id"]
