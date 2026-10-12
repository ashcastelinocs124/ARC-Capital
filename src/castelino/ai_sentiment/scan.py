"""Find posts by tracked accounts (Grok X Search) and fetch their real text from X (oEmbed).

Grok only finds post links. The text and author come from X's public oEmbed endpoint, and a
post counts only if X says its author is on data/ai_sentiment/accounts.csv.
"""

from __future__ import annotations

import html
import logging
import os
import re
from datetime import date

import httpx

log = logging.getLogger(__name__)
XAI_URL = "https://api.x.ai/v1"
MODEL = "grok-4.7"
OEMBED_URL = "https://publish.x.com/oembed"
STATUS = re.compile(r"(?:https?://)?(?:www\.)?(?:x|twitter)\.com/(\w{1,15})/status/(\d+)", re.I)
PROMPT = (
    "List every post from these accounts on {day} that talks about an AI model or AI lab "
    "(Claude, GPT/ChatGPT, Gemini, Grok, DeepSeek, Llama/Meta, Mistral, Qwen, and others). "
    "Include replies and quote posts with an opinion. Output only the post URLs, one per line."
)


def has_key() -> bool:
    return bool(os.environ.get("XAI_API_KEY", "").strip())


def status_urls(text: str, cites: list[str]) -> list[str]:
    """Every x.com status link in the answer and its citations, as https://x.com/<user>/status/<id>."""
    out: list[str] = []
    for src in [text, *cites]:
        for user, sid in STATUS.findall(src or ""):
            u = f"https://x.com/{user.lower()}/status/{sid}"
            if u not in out:
                out.append(u)
    return out


def _grok(tools: list[dict], prompt: str) -> tuple[str, list[str]]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["XAI_API_KEY"], base_url=XAI_URL, timeout=300)
    resp = client.responses.create(model=MODEL, input=prompt, tools=tools)
    cites = []
    for item in resp.output:
        for part in getattr(item, "content", None) or []:
            for ann in getattr(part, "annotations", None) or []:
                if getattr(ann, "url", None):
                    cites.append(ann.url)
    cites += [
        c if isinstance(c, str) else getattr(c, "url", "")
        for c in getattr(resp, "citations", None) or []
    ]
    return resp.output_text or "", cites


def find_posts(handles: list[str], day: date, call=_grok) -> list[str]:
    """One X Search call over up to 20 handles for one day; returns the post URLs found."""
    tools = [
        {
            "type": "x_search",
            "allowed_x_handles": handles,
            "from_date": day.isoformat(),
            "to_date": day.isoformat(),
        }
    ]
    text, cites = call(tools, PROMPT.format(day=day.isoformat()))
    return status_urls(text, cites)


def _get_oembed(url: str) -> dict:
    r = httpx.get(
        OEMBED_URL, params={"url": url, "omit_script": 1}, timeout=20, follow_redirects=True
    )
    r.raise_for_status()
    return r.json()


def parse_oembed(data: dict) -> tuple[str, str]:
    """(author handle, post text) from X's oEmbed reply."""
    author = data["author_url"].rstrip("/").rsplit("/", 1)[-1].lower()
    m = re.search(r"<p[^>]*>(.*?)</p>", data["html"], re.S)
    text = re.sub(r"<[^>]+>", "", m.group(1) if m else "")
    return author, html.unescape(text).strip()


def fetch_posts(urls: list[str], accounts: dict[str, str], get=_get_oembed) -> list[dict]:
    posts = []
    for u in urls:
        try:
            author, text = parse_oembed(get(u))
        except Exception as e:  # noqa: BLE001 - a deleted or private post is just skipped
            log.info("oembed %s: %s", u, e)
            continue
        if author in accounts and text:
            posts.append({"url": u, "author": author, "text": text})
    return posts
