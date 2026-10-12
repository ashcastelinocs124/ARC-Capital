"""Where AI money goes: Ramp AI Index (FRED, monthly) and OpenRouter token share by lab (weekly)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta

import httpx

RAMP = {
    "RAMPAIALL": "Any AI",
    "RAMPAIANTHROPIC": "Anthropic",
    "RAMPAIOPENAI": "OpenAI",
    "RAMPAIXAI": "xAI",
}
RANKINGS_URL = "https://openrouter.ai/rankings"
# ponytail: scraped from the rankings page's embedded data (no API); a redesign raises
# and the card shows unavailable
ROW = re.compile(
    r'"date":"(\d{4}-\d{2}-\d{2}) 00:00:00","model_permaslug":"([^"]+)","variant":"[^"]*",'
    r'"total_completion_tokens":(\d+),"total_prompt_tokens":(\d+)'
)
TOP = 8


def default_fred(series_id: str):
    from castelino.forecast.regime import _fetch_fred_series

    return _fetch_fred_series(series_id)


def ramp(fetch_fred=default_fred) -> dict[str, list[list]]:
    return {
        sid: [[f"{d:%Y-%m}", round(float(v), 2)] for d, v in fetch_fred(sid).items()]
        for sid in RAMP
    }


def get_text(url: str) -> str:
    r = httpx.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text


def openrouter_share(html: str) -> dict:
    """The rankings page embeds the week's top-20 models as rows dated by the week's last day."""
    rows = ROW.findall(html.replace('\\"', '"'))
    if not rows:
        raise RuntimeError("openrouter rankings: 0 rows parsed")
    labs: Counter[str] = Counter()
    for _, slug, c, p in rows:
        labs[slug.split("/")[0]] += int(c) + int(p)
    total = sum(labs.values()) or 1
    top = labs.most_common(TOP)
    other = total - sum(v for _, v in top)
    if other > 0:
        top.append(("other", other))
    end = max(date.fromisoformat(r[0]) for r in rows)
    return {
        "week": [(end - timedelta(days=6)).isoformat(), end.isoformat()],
        "basis": "top-20 models",
        "labs": [{"lab": k, "share": round(100 * v / total, 1), "tokens": v} for k, v in top],
    }
