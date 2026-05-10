"""Build the NYT half of `historical_news.parquet` for the backtest window.

Hits NYT Article Search API once per (month, topic). The free tier is
500 req/day with a 5-second per-call rate limit; pulling 32 months × 8
topics = ~256 calls fits in one quota window.

Schema:
    date     : pd.Timestamp
    source   : "nyt"
    headline : str
    abstract : str
    url      : str

Run AFTER setting NYT_API_KEY in `.env`. The script gracefully exits
with instructions if the key is missing.

Usage:
    python scripts/build_nyt_archive.py
    python scripts/build_nyt_archive.py --start 2023-10 --end 2026-05
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from castelino.backtest.news_archive import (  # noqa: E402
    HISTORICAL_NEWS_FILENAME,
    REQUIRED_COLUMNS,
    historical_news_path,
    merge_source_archives,
)
from castelino.config import get_settings  # noqa: E402

log = logging.getLogger("build_nyt_archive")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


NYT_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
RATE_SLEEP_S = 6  # NYT free tier is 5 req/min, leave headroom
MAX_PAGES_PER_QUERY = 5  # 50 results per topic per month is plenty


def _months_between(start: date, end: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _query_month_topic(
    api_key: str, year: int, month: int, topic: str,
) -> list[dict]:
    """Pull all matches for `(year, month, topic)`. Returns canonical rows."""
    begin = f"{year}{month:02d}01"
    next_y, next_m = (year, month + 1) if month < 12 else (year + 1, 1)
    end = f"{next_y}{next_m:02d}01"
    rows: list[dict] = []
    for page in range(MAX_PAGES_PER_QUERY):
        params = {
            "q": topic,
            "begin_date": begin,
            "end_date": end,
            "page": page,
            "api-key": api_key,
            "sort": "newest",
        }
        try:
            resp = requests.get(NYT_URL, params=params, timeout=20)
        except requests.RequestException as e:
            log.warning("NYT %s/%02d %s page %d net error: %s", year, month, topic, page, e)
            break
        if resp.status_code == 429:
            log.warning("NYT 429 on %s/%02d %s page %d — sleeping 30s", year, month, topic, page)
            time.sleep(30)
            continue
        if resp.status_code != 200:
            log.warning("NYT %s/%02d %s page %d HTTP %d", year, month, topic, page, resp.status_code)
            break
        docs = resp.json().get("response", {}).get("docs", [])
        if not docs:
            break
        for doc in docs:
            try:
                pub = pd.to_datetime(doc.get("pub_date")).tz_localize(None)
            except Exception:
                continue
            rows.append({
                "date": pub,
                "source": "nyt",
                "headline": (doc.get("headline") or {}).get("main", "")[:500],
                "abstract": (doc.get("abstract") or "")[:1000],
                "url": doc.get("web_url", ""),
            })
        time.sleep(RATE_SLEEP_S)
        if len(docs) < 10:
            break
    return rows


def build(start: date, end: date) -> Path:
    cfg = get_settings()
    api_key = cfg.nyt_api_key
    if not api_key:
        raise SystemExit(
            "NYT_API_KEY is not set. Get a free key at developer.nytimes.com "
            "(Article Search API), add it to .env, then re-run.\n"
            "The Sonar/Trump archive can be built independently — see "
            "scripts/build_sonar_trump_archive.py."
        )

    topics = cfg.backtest.nyt_topics
    months = _months_between(start, end)
    log.info("NYT pull: %d months × %d topics = %d calls", len(months), len(topics), len(months) * len(topics))

    out_path = historical_news_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_written = 0

    for (y, m) in months:
        month_rows: list[dict] = []
        for topic in topics:
            log.info("NYT %s/%02d topic=%r", y, m, topic)
            month_rows.extend(_query_month_topic(api_key, y, m, topic))

        if not month_rows:
            log.info("NYT %s/%02d: 0 rows — skipping flush", y, m)
            continue

        df = pd.DataFrame(month_rows)[sorted(REQUIRED_COLUMNS)]
        df = df.drop_duplicates(subset=["source", "url"], keep="first")

        # Per-month flush: merge with existing parquet so partial runs are usable
        parts = [df]
        if out_path.exists():
            parts.append(pd.read_parquet(out_path))
        merged = merge_source_archives(parts)
        merged.to_parquet(out_path)
        total_written = len(merged)
        log.info("NYT %s/%02d: +%d rows; archive total=%d", y, m, len(df), total_written)

    if total_written == 0:
        raise SystemExit("NYT returned zero rows — check key / network / rate limits")
    log.info("NYT done. Total rows in archive: %d at %s", total_written, out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2023-10")
    parser.add_argument("--end", default=date.today().strftime("%Y-%m"))
    args = parser.parse_args()
    sy, sm = (int(x) for x in args.start.split("-"))
    ey, em = (int(x) for x in args.end.split("-"))
    build(date(sy, sm, 1), date(ey, em, 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
