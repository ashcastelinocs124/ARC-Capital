"""Fill in data/adoption/job_boards.csv for universe companies that have no row yet.

job_boards.csv is the hand-checked record (ticker,ats,token) and existing rows are never touched,
so rerunning this after `ckm adoption universe-refresh` only probes the new companies. For each
one it takes the company name from yfinance, tries Greenhouse/Lever tokens derived from it (plus
the ticker), and keeps a hit only when verified: a Greenhouse board's own name must equal the
company name (suffixes like Inc/Corp ignored), since a first-word match picks up unrelated firms
(e.g. "magnolia" is Magnolia Market, not Magnolia Oil & Gas); a Lever board has no name to check,
so its token must be the full squashed name and have postings.

Other platforms can't be guessed from a name, so add those rows by hand after checking the
board returns that company's postings (the 2026-10-05 rows were found with web search, then
checked this way):
  TICKER,workday,tenant/wdN/site          from https://<tenant>.<wdN>.myworkdayjobs.com/<site>
  TICKER,oracle,host/siteNumber           e.g. jpmc.fa.oraclecloud.com/CX_1002
  TICKER,ukg,host/tenant/boardId          from https://<host>/<tenant>/JobBoard/<boardId>/
  AMZN,amazon,amazon                      amazon.jobs search
Companies with no row (custom or in-house career sites) have a missing Hire pillar, not zero
(see adoption/sources/jobs.py).
Usage: uv run python scripts/build_job_boards.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import httpx
import yfinance as yf

D = Path(__file__).resolve().parent.parent / "data" / "adoption"
SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "plc",
    "ltd",
    "limited",
    "holdings",
    "holding",
    "group",
    "the",
    "lp",
    "sa",
    "nv",
    "ag",
    "class",
    "a",
    "b",
    "c",
}


def name_words(name: str) -> list[str]:
    words = re.sub(r"[^a-z0-9 ]+", " ", name.lower().replace("&", " and ")).split()
    return [w for w in words if w not in SUFFIXES]


def candidates(words: list[str], ticker: str) -> list[str]:
    out = ["".join(words), "-".join(words), words[0], ticker.lower()] if words else []
    return list(dict.fromkeys(t for t in out if len(t) >= 3))


def greenhouse(http: httpx.Client, token: str, words: list[str]) -> bool:
    r = http.get(f"https://boards-api.greenhouse.io/v1/boards/{token}")
    if r.status_code != 200:
        return False
    return "".join(name_words(r.json().get("name", ""))) == "".join(words)


def lever(http: httpx.Client, token: str) -> bool:
    r = http.get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json", "limit": 1})
    return r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0


def find_board(http: httpx.Client, name: str, ticker: str) -> tuple[str, str] | None:
    words = name_words(name)
    if not words:
        return None
    for tok in candidates(words, ticker):
        if greenhouse(http, tok, words):
            return "greenhouse", tok
    full = "".join(words)
    if len(full) >= 5 and lever(http, full):  # short tokens collide with unrelated companies
        return "lever", full
    return None


def main() -> int:
    with open(D / "universe.csv", newline="") as f:
        tickers = [r["ticker"] for r in csv.DictReader(f)]
    path = D / "job_boards.csv"
    known: dict[str, tuple[str, str]] = {}
    if path.exists():
        with open(path, newline="") as f:
            known = {r["ticker"]: (r["ats"], r["token"]) for r in csv.DictReader(f)}
    missing = []
    with httpx.Client(timeout=20, follow_redirects=True) as http:
        for t in tickers:
            if t in known:
                continue
            info = yf.Ticker(t).info
            name = info.get("longName") or info.get("shortName") or ""
            hit = find_board(http, name, t) if name else None
            print(f"{t:6} {name[:40]:40} -> {f'{hit[0]}:{hit[1]}' if hit else 'none'}")
            if hit:
                known[t] = hit
            else:
                missing.append(t)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "ats", "token"])
        w.writerows((t, *known[t]) for t in tickers if t in known)
        w.writerows((t, *b) for t, b in known.items() if t not in tickers)  # keep dropped tickers
    covered = sum(t in known for t in tickers)
    print(f"\n{covered}/{len(tickers)} have a board; none: {' '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
