"""Polymarket integration — fetch prediction market context for headlines.

Uses the public Polymarket CLOB API (no auth required) to find contracts
related to a headline and return current prices + 24h changes. This data
enriches the second-pass significance scorer for borderline headlines.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

from castelino.config import get_settings

log = logging.getLogger(__name__)

POLYMARKET_API = "https://clob.polymarket.com"


@dataclass(frozen=True)
class ContractContext:
    question: str
    price: float
    price_24h_ago: float
    volume_24h_usd: float

    @property
    def price_change_pp(self) -> float:
        return round((self.price - self.price_24h_ago) * 100, 1)

    def format_for_prompt(self) -> str:
        direction = "+" if self.price_change_pp >= 0 else ""
        return (
            f'- "{self.question}": {self.price:.0%} '
            f"({direction}{self.price_change_pp}pp 24h, "
            f"${self.volume_24h_usd:,.0f} volume)"
        )


def _cache_dir() -> Path:
    return get_settings().resolved_paths.cache / "polymarket"


def _cache_key(headline: str) -> str:
    return hashlib.sha1(headline.encode()).hexdigest()


def _read_cache(headline: str) -> list[dict] | None:
    cfg = get_settings()
    p = _cache_dir() / f"{_cache_key(headline)}.json"
    if not p.exists():
        return None
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
    ttl = timedelta(minutes=cfg.enrichment.cache_ttl_minutes)
    if (datetime.now(UTC) - mtime) > ttl:
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, KeyError):
        return None


def _write_cache(headline: str, data: list[dict]) -> None:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{_cache_key(headline)}.json").write_text(json.dumps(data, indent=2))


def _extract_keywords(headline: str) -> str:
    stop = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
        "is", "are", "was", "were", "be", "been", "has", "have", "had",
        "will", "would", "could", "should", "may", "might", "than", "that",
        "this", "its", "with", "from", "by", "as", "but", "not", "no", "so",
        "if", "up", "down", "out", "more", "less", "over", "under", "new",
        "says", "said", "report", "reports", "according",
    }
    words = [w.strip(".,;:!?\"'()") for w in headline.lower().split()]
    keywords = [w for w in words if w and w not in stop and len(w) > 2]
    return " ".join(keywords[:5])


def fetch_related_contracts(headline: str) -> list[ContractContext]:
    """Search Polymarket for contracts related to a headline."""
    cfg = get_settings()
    if not cfg.enrichment.polymarket_enabled:
        return []

    cached = _read_cache(headline)
    if cached is not None:
        return [ContractContext(**c) for c in cached]

    query = _extract_keywords(headline)
    if not query:
        return []

    try:
        resp = requests.get(
            f"{POLYMARKET_API}/markets",
            params={"next_cursor": "MA==", "limit": 5},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("Polymarket API failed: %s", e)
        return []

    markets = data if isinstance(data, list) else data.get("data", data.get("markets", []))
    query_words = set(query.split())

    scored: list[tuple[int, dict]] = []
    for m in markets:
        question = m.get("question", "")
        q_lower = question.lower()
        overlap = sum(1 for w in query_words if w in q_lower)
        if overlap >= 2:
            scored.append((overlap, m))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: list[ContractContext] = []
    for _, m in scored[:3]:
        tokens = m.get("tokens", [])
        price = 0.0
        if tokens:
            price = float(tokens[0].get("price", 0))

        volume = float(m.get("volume", 0))
        price_24h = price - float(m.get("price_change_24h", 0))

        ctx = ContractContext(
            question=m.get("question", "Unknown"),
            price=price,
            price_24h_ago=max(price_24h, 0.0),
            volume_24h_usd=volume,
        )
        results.append(ctx)

    cache_data = [
        {"question": c.question, "price": c.price,
         "price_24h_ago": c.price_24h_ago, "volume_24h_usd": c.volume_24h_usd}
        for c in results
    ]
    _write_cache(headline, cache_data)
    return results
