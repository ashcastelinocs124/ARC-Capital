"""Polymarket economy markets: Gamma API for odds and moves, CLOB for 7-day history. No key."""

from __future__ import annotations

import json

import requests

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
            d1 = (m.get("oneDayPriceChange") or 0) * 100
            w1 = (m.get("oneWeekPriceChange") or 0) * 100
            rows.append((abs(w1) + abs(d1), e, m, yes, d1, w1, token))
    rows.sort(key=lambda r: r[0], reverse=True)
    out: list[Fact] = []
    for _, e, m, yes, d1, w1, token in rows[:top]:
        q = m.get("question") or e.get("title", "")
        out.append(
            Fact(
                id=f"P{len(out) + 1}",
                text=f'Polymarket "{q}": Yes {yes:.1f}% (1d {d1:+.1f}pp, 1w {w1:+.1f}pp)',
                numbers=[round(yes, 4), round(d1, 4), round(w1, 4)],
                provenance="data",
                series=SeriesRef(kind="daily", provider="polymarket", id=token, label=q),
                source_title=f"Polymarket: {e.get('title', '')}",
                source_url=f"https://polymarket.com/event/{e.get('slug', '')}",
            )
        )
    return out
