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


def price_history(
    token: str, get=requests.get, start: int | None = None, end: int | None = None
) -> list[tuple[int, float]]:
    """Daily points for the last week, or hourly points between start and end (unix seconds)."""
    params: dict = {"market": token, "interval": "1w", "fidelity": 1440}
    if start is not None and end is not None:
        params = {"market": token, "startTs": start, "endTs": end, "fidelity": 60}
    r = get(f"{CLOB}/prices-history", params=params, timeout=20)
    r.raise_for_status()
    return [(int(p["t"]), float(p["p"])) for p in r.json().get("history", [])]


def _asof_odds(hist: list[tuple[int, float]], end: int) -> tuple[float, dict[str, float]] | None:
    """Yes price at `end` and its 1d / 1w moves, from price history; None if no point by `end`."""

    def at(t: int) -> float | None:
        ps = [p for ts, p in hist if ts <= t]
        return ps[-1] if ps else None

    now = at(end)
    if now is None:
        return None
    moves = {
        k: (now - v) * 100
        for k, dt in (("1d", 86400), ("1w", 7 * 86400))
        if (v := at(end - dt)) is not None
    }
    return now * 100, moves


def facts(events: list[dict], top: int = 8, history_fn=None, day=None) -> list[Fact]:
    """Biggest movers. With `day`, odds and moves come from price history up to that day's end."""
    if day is not None:
        from castelino.agents.update.asof import day_end_ts

        end = day_end_ts(day)
        history_fn = history_fn or (
            lambda tok, start, end: price_history(tok, start=start, end=end)
        )
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
            if day is not None:
                try:
                    got = _asof_odds(history_fn(token, end - 10 * 86400, end), end)
                except Exception:  # noqa: BLE001 — skip a market whose history won't load
                    got = None
                if got is None:
                    continue  # the market didn't exist yet
                yes, moves = got
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
