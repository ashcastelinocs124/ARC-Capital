"""Universe: top N by market cap per size bucket, from a user-maintained seed list."""

from __future__ import annotations

import csv
import logging
from collections.abc import Callable
from pathlib import Path

from castelino.adoption.models import BUCKETS, Company

log = logging.getLogger(__name__)

# yfinance sector names -> GICS sector names
SECTOR_MAP = {
    "Technology": "Information Technology",
    "Communication Services": "Communication Services",
    "Consumer Cyclical": "Consumer Discretionary",
    "Financial Services": "Financials",
    "Healthcare": "Health Care",
    "Industrials": "Industrials",
    "Consumer Defensive": "Consumer Staples",
    "Energy": "Energy",
    "Utilities": "Utilities",
    "Basic Materials": "Materials",
    "Real Estate": "Real Estate",
}


def load_seed(path: Path) -> list[tuple[str, str]]:
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            bucket = r["bucket"].strip().lower()
            if bucket not in BUCKETS:
                raise ValueError(
                    f"unknown bucket {bucket!r} for {r['ticker']} (expected one of {BUCKETS})"
                )
            out.append((r["ticker"].strip().upper(), bucket))
    return out


def build_universe(
    seed: list[tuple[str, str]], info_fn: Callable[[str], dict], top_n: int
) -> list[Company]:
    by_bucket: dict[str, list[Company]] = {b: [] for b in BUCKETS}
    seen: set[str] = set()
    for ticker, bucket in seed:
        if ticker.upper() in seen:  # a duplicate would collide on the store's (period, ticker) key
            log.warning("universe: duplicate ticker %s (bucket %s) ignored", ticker, bucket)
            continue
        seen.add(ticker.upper())
        try:
            info = info_fn(ticker)
        except Exception as e:  # one bad ticker never blocks the rest
            log.warning("universe: lookup failed for %s: %s", ticker, e)
            continue
        cap, sector = info.get("marketCap"), SECTOR_MAP.get(info.get("sector"))
        if not cap or not sector:
            log.warning(
                "universe: skipping %s (marketCap=%s sector=%s)", ticker, cap, info.get("sector")
            )
            continue
        name = info.get("shortName") or info.get("longName") or ""
        by_bucket[bucket].append(Company(ticker.upper(), bucket, sector, float(cap), name))
    out: list[Company] = []
    for b in BUCKETS:
        out += sorted(by_bucket[b], key=lambda c: -c.market_cap)[:top_n]
    return out


def yf_info(ticker: str) -> dict:
    import yfinance as yf

    return yf.Ticker(ticker).info


def save_universe(path: Path, companies: list[Company]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "bucket", "sector", "market_cap", "name"])
        w.writerows([[c.ticker, c.bucket, c.sector, c.market_cap, c.name] for c in companies])


def load_universe(path: Path) -> list[Company]:
    with open(path, newline="") as f:
        return [
            Company(
                r["ticker"], r["bucket"], r["sector"], float(r["market_cap"]), r.get("name") or ""
            )
            for r in csv.DictReader(f)
        ]
