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
from functools import lru_cache
from urllib.parse import quote

import httpx

TWEETS = "https://api.x.com/2/tweets"
MEDIA = "https://api.x.com/2/media/upload"
LIMIT = 280
_URL = re.compile(r"https?://\S+")
# Emoji and pictographs (plus the variation selector, joiner and keycap that build them) and one space after;
# arrows like → are text and stay.
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\u231a\u231b\u23e9-\u23fa\ufe0f\u200d\u20e3] ?"
)
KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")


def can_post() -> bool:
    return all(os.getenv(k) for k in KEYS)


def xlen(text: str) -> int:
    """X's weighted length: a link counts 23, most Latin text 1 per character, emoji and CJK 2."""
    text = _URL.sub("x" * 23, text)
    return sum(1 if ord(c) <= 4351 or 8192 <= ord(c) <= 8247 else 2 for c in text)


# Acronyms written in brackets that are not tickers, so never turned into cashtags or checked as one.
NOT_TICKERS = {
    "AI", "API", "BLS", "BOJ", "CEO", "CFO", "CPI", "ECB", "EPS", "ET", "ETF", "EU", "FDA", "FED",
    "FOMC", "GDP", "GPU", "HBM", "IMF", "IPO", "ISM", "LLM", "NAHB", "OPEC", "PCE", "PMI", "PPI",
    "SEC", "UK", "US", "USD", "WTI", "YOY",
}  # fmt: skip
# "SpaceX (SPCX)" or "Taiwan Semiconductor (TSM)": up to 5 capitalised words, then the ticker in brackets
_NAMED = re.compile(r"(?:\b[A-Z][\w&.'’-]*\s+){0,5}\(([A-Z]{1,5}(?:[.-][A-Z]{1,2})?)\)")
# a cashtag, whether code made it or the model wrote it: "$TSLA", never "$2.5"
_CASHTAG = re.compile(r"\$([A-Z]{1,5}(?:[.-][A-Z]{1,2})?)\b")


@lru_cache(maxsize=256)
def trades(ticker: str) -> bool:
    """True if Yahoo Finance has a close for `ticker` in the last 10 days. An error (Yahoo down)
    counts as True: an outage never blocks a post."""
    import yfinance as yf

    try:
        return not yf.Ticker(ticker).history(period="10d").empty
    except Exception as e:  # noqa: BLE001
        print(f"  ticker check for {ticker} failed: {e}")
        return True


def cashtags(text: str, lookup=None) -> str:
    """Stocks as X cashtags only (user rule, 2026-10-21): "SpaceX (SPCX) beat" -> "$SPCX beat", the
    capitalised name before the brackets going with them. Only a ticker that trades is turned, so
    "(CPI)" or a wrong "(TSMC)" stays as written; "Energy stocks (XLE)" keeps its lower-case words.
    X allows one cashtag per post, so only the first is kept and later ones lose their "$"."""
    lookup = lookup or trades

    def sub(m: re.Match) -> str:
        t = m.group(1)
        return f"${t}" if t not in NOT_TICKERS and lookup(t) else m.group(0)

    n = 0

    def first(m: re.Match) -> str:  # X refuses a post with more than one cashtag (403)
        nonlocal n
        n += 1
        return m.group(0) if n == 1 else m.group(1)

    return _CASHTAG.sub(first, _NAMED.sub(sub, text))


def no_emoji(text: str) -> str:
    """No emoji in any X or Substack post (the user's rule, 2026-10-20): post() and substack.py apply it."""
    return _EMOJI.sub("", text)


def drafts(kind: str, title: str, takeaways: list[str], url: str) -> list[str]:
    """A thread for both kinds: the title, one post per takeaway (≤5), then the link."""
    end = (
        "Full note on Substack"
        if kind == "daily"
        else "The full deep dive, with charts and sources"
    )
    return [
        title,
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


def _auth_header(method: str, url: str, query: dict[str, str] | None = None) -> str:
    """`url` without its query string; a GET's `query` params are signed too (OAuth 1.0a)."""
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
        method,
        url,
        oauth | (query or {}),
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_SECRET"],
    )
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))


def as_jpeg(data: bytes, width: int = 1600) -> bytes:
    """A cover as a JPEG X accepts (images must be under 5 MB): at most `width` px wide."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


def upload_image(data: bytes) -> str:
    """Upload an image for a post; returns its media id. Raises with X's message on failure."""
    body = {"media": base64.b64encode(as_jpeg(data)).decode(), "media_category": "tweet_image"}
    r = httpx.post(
        MEDIA, json=body, headers={"Authorization": _auth_header("POST", MEDIA)}, timeout=60
    )
    if r.status_code >= 400:
        raise RuntimeError(f"X image upload said {r.status_code}: {r.text[:300]}")
    return r.json()["data"]["id"]


def post(text: str, reply_to: str | None = None, media_id: str | list[str] | None = None) -> str:
    """One post; returns its id. Raises with X's message on failure. media_id: one image or up to 4."""
    body: dict = {"text": cashtags(no_emoji(text)).strip()}
    if reply_to:
        body["reply"] = {"in_reply_to_tweet_id": reply_to}
    if media_id:
        body["media"] = {"media_ids": [media_id] if isinstance(media_id, str) else media_id[:4]}
    r = httpx.post(
        TWEETS, json=body, headers={"Authorization": _auth_header("POST", TWEETS)}, timeout=30
    )
    if r.status_code >= 400:
        raise RuntimeError(f"X said {r.status_code}: {r.text[:300]}")
    return r.json()["data"]["id"]
