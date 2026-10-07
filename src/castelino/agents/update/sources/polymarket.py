"""Polymarket economy markets: Gamma API for odds and moves, CLOB for 7-day history. No key."""

from __future__ import annotations

import json

import requests

from castelino.agents.update.facts import numbers_in
from castelino.agents.update.models import Fact, SeriesRef

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def fetch_events(tag: str = "economy", limit: int = 10, get=requests.get) -> list[dict]:
    r = get(
        f"{GAMMA}/events",
        params={
            "tag_slug": tag,
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": limit,
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def price_history(token: str, get=requests.get) -> list[tuple[int, float]]:
    r = get(
        f"{CLOB}/prices-history",
        params={"market": token, "interval": "1w", "fidelity": 1440},
        timeout=20,
    )
    r.raise_for_status()
    return [(int(p["t"]), float(p["p"])) for p in r.json().get("history", [])]


def facts(events: list[dict], top: int = 8) -> list[Fact]:
    rows = []
    for e in events:
        for m in e.get("markets") or []:
            if m.get("closed") or not m.get("active", True):
                continue
            try:
                yes = float(json.loads(m["outcomePrices"])[0]) * 100
                token = json.loads(m["clobTokenIds"])[0]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            # a missing window stays missing: never report an invented "+0.0pp" move
            moves = {
                k: m[key] * 100
                for k, key in (("1d", "oneDayPriceChange"), ("1w", "oneWeekPriceChange"))
                if isinstance(m.get(key), int | float)
            }
            rows.append((sum(abs(v) for v in moves.values()), e, m, yes, moves, token))
    rows.sort(key=lambda r: r[0], reverse=True)
    out: list[Fact] = []
    for _, e, m, yes, moves, token in rows[:top]:
        q = m.get("question") or e.get("title", "")
        window = ", ".join(f"{k} {v:+.1f}pp" for k, v in moves.items())
        out.append(
            Fact(
                id=f"P{len(out) + 1}",
                text=f'Polymarket "{q}": Yes {yes:.1f}%' + (f" ({window})" if window else ""),
                # figures in the question itself ("25 bps") are source data too
                numbers=[*numbers_in(q), round(yes, 4), *(round(v, 4) for v in moves.values())],
                provenance="data",
                series=SeriesRef(kind="daily", provider="polymarket", id=token, label=q),
                source_title=f"Polymarket: {e.get('title', '')}",
                source_url=f"https://polymarket.com/event/{e.get('slug', '')}",
            )
        )
    return out
