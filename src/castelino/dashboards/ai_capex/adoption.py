"""The public slice of ARC's AI Adoption Index: its talk pillar only (which companies make a concrete AI
claim in their latest filing, and how deep it goes), by size bucket and sector, outside the dashboard's
own companies. Read-only: it never starts an index run. No hire or spend pillar, no composite score."""

from __future__ import annotations

import re

from castelino.adoption.store import AdoptionStore

BUCKETS = ("all", "large", "mid", "small")
# filings rarely name the AI tools a company buys; when they name one it's mostly their own product
PRODUCTS = re.compile(
    r"\b(ChatGPT|OpenAI|Copilot|Claude|Anthropic|Gemini|Agentforce|Bedrock|watsonx|Llama)\b"
)
QUOTE_MAX = 220


def _bucket(rows: list[dict]) -> dict:
    n = len(rows)
    claimed = [r for r in rows if r["depth"]]
    counts = [sum(1 for r in claimed if r["depth"] == d) for d in (1, 2, 3)]
    sectors: dict[str, list[dict]] = {}
    for r in rows:
        sectors.setdefault(r["sector"], []).append(r)
    by_sector = [
        {
            "sector": s,
            "n": len(rs),
            "pct": round(sum(1 for r in rs if r["depth"]) / len(rs) * 100),
            "thin": len(rs) < 5,
        }
        for s, rs in sectors.items()
    ]
    by_sector.sort(key=lambda s: (-s["n"], -s["pct"], s["sector"]))
    best = sorted(claimed, key=lambda r: (-r["depth"], -r["market_cap"], r["ticker"]))[:2]
    return {
        "n": n,
        "with_claim": len(claimed),
        "pct": round(len(claimed) / n * 100) if n else None,
        "depth": [round(c / len(claimed) * 100) for c in counts] if claimed else [0, 0, 0],
        "sectors": by_sector[:6],
        "quotes": [
            {
                "name": r["name"],
                "ticker": r["ticker"],
                "quote": r["top"]
                if len(r["top"]) <= QUOTE_MAX
                else r["top"][: QUOTE_MAX - 1] + "…",
            }
            for r in best
        ],
    }


def talk_slice(
    store: AdoptionStore, exclude: set[str], names: dict[str, str] | None = None
) -> dict | None:
    periods = store.periods()
    if not periods:
        return None
    period = periods[-1]
    rows, named, total = [], 0, 0
    for c in store.companies(period):
        if c["ticker"] in exclude:
            continue
        claims = store.claims_for(c["ticker"], c["accession"], limit=1000)
        total += len(claims)
        named += sum(1 for cl in claims if PRODUCTS.search(cl["quote"]))
        rows.append(
            {
                "ticker": c["ticker"],
                "name": (names or {}).get(c["ticker"], c["ticker"]),
                "bucket": c["bucket"],
                "sector": c["sector"],
                "market_cap": c["market_cap"] or 0.0,
                "depth": max((cl["depth"] for cl in claims), default=0),
                "top": claims[0]["quote"] if claims else "",  # claims_for: deepest first
            }
        )
    return {
        "period": period,
        "product_claims": {"named": named, "total": total},
        "buckets": {
            b: _bucket([r for r in rows if b == "all" or r["bucket"] == b]) for b in BUCKETS
        },
        "source": {
            "title": "ARC AI Adoption Index (talk pillar, SEC filings)",
            "url": "https://arcresearch.markets/docs",
        },
    }
