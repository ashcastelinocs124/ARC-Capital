"""What the models cost (admin → Costs): each logged call's tokens × that model's list price,
plus the Fly.io server at its list price.

Reads the benchmark call logs (benchmark.py), so it covers every provider we call. An estimate,
not the invoice: the log keeps total input tokens only, so cached-input discounts aren't counted,
and each OpenAI web search adds one assumed call fee. A model missing from PRICES is reported as
unpriced (usd None), never as $0.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache

from castelino import benchmark

PRICES_AS_OF = "2026-10-15"
# $ per million tokens (in, out), list prices on PRICES_AS_OF. ponytail: DeepSeek is priced at a
# no-data-retention host's rate; Trade Lab's Meter uses OpenRouter's reported cost when a reply carries one.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-6-sol": (2.0, 10.0),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.5": (5.0, 30.0),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-image-2": (5.0, 30.0),  # text prompt in, image tokens out
    "claude-opus-5-5": (4.0, 20.0),
    "deepseek/deepseek-v4-pro": (1.30, 2.60),
    "anthropic/claude-haiku-5.5": (0.10, 0.50),  # Trade Lab Talk 2, OpenRouter list 2026-10-16
    "anthropic/claude-sonnet-5.5": (2.0, 10.0),
    # chart desk models: OpenRouter's listed prices on 2026-10-16
    "moonshotai/kimi-k3": (0.30, 11.59),
    "qwen/qwen3.8-max-0902": (2.0, 6.0),
    "z-ai/glm-5.3": (0.08, 4.80),
    "mistralai/mistral-large-4-0": (0.68, 2.09),
    "deepseek/deepseek-v4.1-flash": (0.04, 0.68),
}
SEARCH_FEE = 0.01  # assumed $ per OpenAI web search call (2025 rate); confirm on the invoice

# The Fly.io server, at list price: Fly has no billing API (flyctl has no billing command), so this
# is the fly.toml [[vm]] size ($13.39/month for shared-cpu-2x, 2 GB, in iad) plus the 3 GB volume at
# $0.15/GB. ponytail: update it with fly.toml. Shared IPs are free; bandwidth isn't counted.
FLY_USD_MONTH = 13.39 + 3 * 0.15
FLY_SINCE = "2026-10-13"  # a card was added that day; the free trial before it cost nothing


def provider(model: str) -> str:
    if model.startswith("claude"):
        return "anthropic"
    return "openrouter" if "/" in model else "openai"


def usd(row: dict) -> float | None:
    """One logged call's $: tokens × price, plus the search fee for a successful web search."""
    price = PRICES.get(row["model"])
    if price is None:
        return None
    fee = SEARCH_FEE if row["agent"] == "web_search" and not row.get("error") else 0.0
    tin, tout = row.get("tokens_in") or 0, row.get("tokens_out") or 0
    return (tin * price[0] + tout * price[1]) / 1e6 + fee


@lru_cache(maxsize=512)
def _day(root: str, day: str, size: int) -> tuple[dict, ...]:
    # ponytail: keyed on the log folder and the file's size, so a finished day is read once and
    # today re-reads only after it grows. Holds the grouped rows, not the logged inputs/outputs.
    groups: dict[tuple[str, str], dict] = {}
    for r in benchmark.read("calls", day):
        g = groups.setdefault(
            (r["agent"], r["model"]),
            {
                "day": day,
                "agent": r["agent"],
                "model": r["model"],
                "provider": provider(r["model"]),
                "calls": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "usd": 0.0 if r["model"] in PRICES else None,
            },
        )
        g["calls"] += 1
        g["tokens_in"] += r.get("tokens_in") or 0
        g["tokens_out"] += r.get("tokens_out") or 0
        if g["usd"] is not None:
            g["usd"] += usd(r)
    return tuple(groups.values())


def summary(days: int = 30, today: date | None = None) -> dict:
    """Calls, tokens and $ per (day, agent, model) over the last `days` days, plus one Fly.io row
    a day (provider "fly", no calls); the page groups them."""
    today = today or date.today()
    rows = []
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        p = benchmark.root() / "calls" / f"{day}.jsonl.gz"
        if p.exists():
            rows += _day(str(p.parent), day, os.path.getsize(p))
        if day >= FLY_SINCE:
            rows.append(
                {
                    "day": day,
                    "agent": "fly_server",
                    "model": "fly.io",
                    "provider": "fly",
                    "calls": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "usd": FLY_USD_MONTH / 30,
                }
            )
    return {
        "days": days,
        "today": today.isoformat(),
        "prices_as_of": PRICES_AS_OF,
        "prices": {m: list(p) for m, p in PRICES.items()},
        "search_fee": SEARCH_FEE,
        "fly_usd_month": FLY_USD_MONTH,
        "rows": rows,
    }
