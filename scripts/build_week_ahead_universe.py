"""One-off: write data/week_ahead/universe.csv (S&P 500 + hand-kept AI names).

Rerun by hand when the index changes.
"""

import csv
import io
from pathlib import Path

import httpx

SRC = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
AI_EXTRA = [  # big non-S&P AI names; tickers with a '.' come from yfinance (no US listing)
    ("TSM", "Taiwan Semiconductor"),
    ("ASML", "ASML Holding"),
    ("005930.KS", "Samsung Electronics"),
    ("9984.T", "SoftBank Group"),
]
OUT = Path(__file__).resolve().parents[1] / "data" / "week_ahead" / "universe.csv"

rows = list(csv.DictReader(io.StringIO(httpx.get(SRC, timeout=30, follow_redirects=True).text)))
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ticker", "name", "group"])
    for r in sorted(rows, key=lambda r: r["Symbol"]):
        w.writerow([r["Symbol"], r["Security"], "sp500"])
    for t, n in AI_EXTRA:
        w.writerow([t, n, "ai_extra"])
print(f"wrote {len(rows)} + {len(AI_EXTRA)} rows to {OUT}")
