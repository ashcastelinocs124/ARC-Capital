"""AI model launches: confirmed (OpenRouter's model list) and credibly reported (one cited web search)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta

import httpx

MODELS_URL = "https://openrouter.ai/api/v1/models"
VARIANT = re.compile(r"\((batch|free)\)|:(free|batch)\b", re.I)
MD_LINK = re.compile(r"\(?\[[^\]]*\]\([^)]*\)\)?")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
SYSTEM = (
    "You track AI model releases. Only include releases announced by the lab itself or reported "
    "by a named news outlet; never anonymous social-media rumours. Output one release per line "
    "exactly as: Lab | Model | expected date (YYYY-MM-DD if a day is known, else the window). "
    "No other text. If there are none, output NONE."
)


def get_json(url: str) -> dict:
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def _ts(d: date) -> float:
    return datetime.combine(d, time.min, UTC).timestamp()


def launched(monday: date, friday: date, get_json=get_json) -> list[dict]:
    """Models OpenRouter added from 7 days before the week through Friday."""
    lo, hi = _ts(monday - timedelta(days=7)), _ts(friday + timedelta(days=1))
    seen: set[str] = set()
    out = []
    models = sorted(get_json(MODELS_URL).get("data") or [], key=lambda m: m.get("created") or 0)
    for m in models:
        created, mid = m.get("created") or 0, m.get("id") or ""
        name = m.get("name") or mid
        slug = m.get("canonical_slug") or mid
        if not lo <= created < hi or VARIANT.search(name) or VARIANT.search(mid) or slug in seen:
            continue
        seen.add(slug)
        lab, _, short = name.partition(": ")
        if not short:
            lab, short = mid.split("/")[0], name
        out.append(
            {
                "date": datetime.fromtimestamp(created, UTC).date().isoformat(),
                "time_et": None,
                "kind": "ai",
                "name": short,
                "lab": lab,
                "status": "launched",
                "when": None,
                "source_url": f"https://openrouter.ai/{mid}",
            }
        )
    return out


def reported(monday: date, search) -> list[dict]:
    """Cited 'Lab | Model | when' lines for the next 14 days; an uncited line is dropped."""
    user = f"AI model releases expected between {monday} and {monday + timedelta(days=14)}."
    text, cites = search(SYSTEM, user)
    out, pos = [], 0
    for line in text.split("\n"):
        start, end = pos, pos + len(line)
        pos = end + 1
        url = next((u for _, u, s, e in cites if s < end and e > start), None)
        parts = [MD_LINK.sub("", p).strip(" -*•\t") for p in line.split("|")]
        if not url or len(parts) != 3 or not all(parts):
            continue
        lab, name, when = parts
        iso = ISO.search(when)
        out.append(
            {
                "date": iso.group(0) if iso else None,
                "time_et": None,
                "kind": "ai",
                "name": name,
                "lab": lab,
                "status": "reported",
                "when": when,
                "source_url": url,
            }
        )
    return out
