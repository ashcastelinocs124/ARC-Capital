"""Live data for the research agents, read from the JSON that two public pages embed (Next.js flight data):
the Ramp AI Index (the monthly share of U.S. businesses on Ramp paying for AI, by vendor, industry and size,
and weekly token spend by model maker) and OpenRouter's rankings (the most-used models now, each tagged
open-weight or closed from OpenRouter's models API). Every figure becomes a dated fact, so the writer's
latest-data check can see its date. A page whose layout changed raises ToolError and the agent moves on."""

from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache

import httpx

from castelino.agents.update.models import Fact
from castelino.agents.weekly.tools import ToolError

RAMP = "https://ramp.com/data/ai-index"
OPENROUTER = "https://openrouter.ai/rankings"
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
RAMP_VIEWS = ("overall", "vendors", "industries", "sizes", "tokens")
MAKERS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "xai": "xAI",
    "meta": "Meta",
}
TOP = 10  # OpenRouter models listed
_UA = {"User-Agent": "Mozilla/5.0 (compatible; ARC Research)"}


def _get(url: str) -> str:
    r = httpx.get(url, headers=_UA, timeout=60, follow_redirects=True)
    r.raise_for_status()
    return r.text


@lru_cache(maxsize=4)
def _flight(url: str, day: str) -> str:
    """The page's flight data as one string; fetched once a day per process (Ramp's page is ~11 MB)."""
    out = []
    for c in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', _get(url), flags=re.S):
        try:
            out.append(json.loads(f'"{c}"'))
        except ValueError:
            continue
    return "".join(out)


def _series(url: str, key: str) -> list:
    flight = _flight(url, date.today().isoformat())
    i = flight.find(f'"{key}":[')
    if i < 0:
        raise ToolError(f"the page no longer has {key}; its layout may have changed")
    rows, _ = json.JSONDecoder().raw_decode(flight, i + len(key) + 3)
    return rows


def _month(d: str) -> str:
    return f"{date.fromisoformat(d):%B %Y}"


def _pp(x: float) -> str:
    return f"{x:+.1f} pp"


def _fact(text: str, numbers: list[float], title: str, url: str) -> Fact:
    return Fact(
        id="tmp", text=text, numbers=numbers, provenance="data", source_title=title, source_url=url
    )


def _latest(rows: list[dict], label: str, what: str) -> Fact:
    last = max(r["date_month"] for r in rows)
    top = sorted(
        (r for r in rows if r["date_month"] == last), key=lambda r: -r["adoption_rate_pct"]
    )
    parts = ", ".join(f"{r[label]} {r['adoption_rate_pct']:.1f}%" for r in top)
    text = f"Ramp AI Index, {_month(last)}: {what}: {parts}."
    return _fact(text, [round(r["adoption_rate_pct"], 1) for r in top], "Ramp AI Index", RAMP)


def ramp(view: str) -> list[Fact]:
    if view not in RAMP_VIEWS:
        raise ToolError(f"view must be one of {', '.join(RAMP_VIEWS)}")
    if view == "overall":
        rows = sorted(_series(RAMP, "adoptionOverall"), key=lambda r: r["date_month"])[-6:]
        now = rows[-1]
        trail = ", ".join(f"{_month(r['date_month'])} {r['adoption_rate_pct']:.1f}%" for r in rows)
        changes = [
            (now[k], w)
            for k, w in (("mom_change_pp", "month"), ("yoy_change_pp", "year"))
            if now.get(k) is not None
        ]
        said = f" ({', '.join(f'{_pp(x)} on the {w}' for x, w in changes)})" if changes else ""
        text = (
            f"Ramp AI Index, {_month(now['date_month'])}: {now['adoption_rate_pct']:.1f}% of U.S. businesses on "
            f"Ramp paid for AI{said}. Last six months: {trail}."
        )
        nums = [round(r["adoption_rate_pct"], 1) for r in rows] + [round(x, 1) for x, _ in changes]
        return [_fact(text, nums, "Ramp AI Index", RAMP)]
    if view == "vendors":
        return [
            _latest(
                _series(RAMP, "adoptionVendor"),
                "vendor",
                "share of U.S. businesses paying each AI vendor",
            )
        ]
    if view == "industries":
        rows = _series(RAMP, "adoptionIndustry")
        return [
            _latest(rows, "naics_sector", "share of U.S. businesses paying for AI, by industry")
        ]
    if view == "sizes":
        rows = _series(RAMP, "adoptionSize")
        return [_latest(rows, "business_size", "share of U.S. businesses paying for AI, by size")]
    rows = [r for r in _series(RAMP, "tokenPrices") if r["token_type"] == "all_tokens"]
    last = max(r["usage_date"] for r in rows)
    week = [r for r in rows if r["usage_date"] == last]
    tokens, cost = sum(r["token_count_7d"] for r in week), sum(r["token_cost_usd_7d"] for r in week)
    week.sort(key=lambda r: -r["token_count_7d"])
    name = lambda r: MAKERS.get(r["model_maker"], r["model_maker"].title())  # noqa: E731
    t = [round(100 * r["token_count_7d"] / tokens, 1) for r in week]
    c = [round(100 * r["token_cost_usd_7d"] / cost, 1) for r in week]
    d = date.fromisoformat(last)
    text = (
        f"Ramp AI Index, week to {d:%B} {d.day}, {d.year}: share of AI tokens businesses bought through Ramp, by "
        f"model maker: {', '.join(f'{name(r)} {x:.1f}%' for r, x in zip(week, t, strict=True))}; share of "
        f"token spend: {', '.join(f'{name(r)} {x:.1f}%' for r, x in zip(week, c, strict=True))}."
    )
    return [_fact(text, t + c, "Ramp AI Index", RAMP)]


@lru_cache(maxsize=2)
def _open_weights(day: str) -> dict[str, bool]:
    """Model id → open weights (OpenRouter lists a Hugging Face id for open-weight models)."""
    return {
        m["id"]: bool(m.get("hugging_face_id")) for m in json.loads(_get(OPENROUTER_MODELS))["data"]
    }


def openrouter() -> list[Fact]:
    day = date.today()
    ranked = sorted(_series(OPENROUTER, "itemListElement"), key=lambda r: r["position"])[:TOP]
    if not ranked:
        raise ToolError("OpenRouter's rankings list is empty")
    weights = _open_weights(day.isoformat())
    tag = {True: "open weights", False: "closed"}
    parts, n_open = [], 0
    for r in ranked:
        is_open = weights.get(r["item"].removeprefix("https://openrouter.ai/"))
        n_open += bool(is_open)
        parts.append(f"{r['position']} {r['name']} ({tag.get(is_open, 'weights unknown')})")
    text = (
        f"OpenRouter's most-used models by tokens, rankings as of {day:%B} {day.day}, {day.year}: "
        f"{', '.join(parts)}. {n_open} of the top {len(ranked)} are open-weight."
    )
    return [_fact(text, [float(n_open), float(len(ranked))], "OpenRouter rankings", OPENROUTER)]
