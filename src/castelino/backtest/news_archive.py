"""Historical news archive — pluggable per-source parquet store.

Sources supported in v1:
  - `nyt`         : NYT Article Search API (broad macro coverage)
  - `sonar_trump` : Perplexity Sonar one-call-per-month for Trump events
                    (cheap, cited, fills the gap NYT undercounts)

The archive is a single parquet (`historical_news.parquet`) with one row
per headline:
    columns = [date, source, headline, abstract, url]

`headlines_for(d)` returns up to N rows that fall in the trailing 24h
window — i.e. the news a live system would have seen by `d`.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from castelino.config import get_settings

log = logging.getLogger(__name__)


HISTORICAL_NEWS_FILENAME = "historical_news.parquet"

REQUIRED_COLUMNS = {"date", "source", "headline", "abstract", "url"}


class NewsArchiveError(RuntimeError):
    """Raised when the historical news parquet is missing or malformed."""


class HistoricalHeadline(BaseModel):
    date: datetime
    source: str
    headline: str
    abstract: str
    url: str


def historical_news_path() -> Path:
    return get_settings().resolved_paths.cache / HISTORICAL_NEWS_FILENAME


@lru_cache(maxsize=1)
def _load_archive(path_str: str) -> pd.DataFrame:
    p = Path(path_str)
    if not p.exists():
        raise NewsArchiveError(
            f"Historical news archive not found: {p}. "
            f"Run `python scripts/build_nyt_archive.py` and "
            f"`python scripts/build_sonar_trump_archive.py` first."
        )
    df = pd.read_parquet(p)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise NewsArchiveError(
            f"Historical news missing columns: {missing}"
        )
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def clear_cache() -> None:
    _load_archive.cache_clear()


def headlines_for(
    d: date,
    *,
    window_hours: int = 24,
    max_items: int = 30,
) -> list[HistoricalHeadline]:
    """Return up to `max_items` headlines from `[d-window_hours, d]`.

    The window is "look-back" — what a live system would have seen by
    end-of-day on `d`. Sources are merged: NYT and Sonar/Trump rows
    appear together, sorted by date desc.
    """
    df = _load_archive(str(historical_news_path()))
    end = pd.Timestamp(datetime.combine(d, datetime.max.time()))
    start = end - pd.Timedelta(hours=window_hours)
    sub = df[(df["date"] >= start) & (df["date"] <= end)]
    if sub.empty:
        return []
    sub = sub.sort_values("date", ascending=False).head(max_items)
    out: list[HistoricalHeadline] = []
    for _, row in sub.iterrows():
        ts = row["date"].to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        out.append(HistoricalHeadline(
            date=ts,
            source=str(row["source"]),
            headline=str(row["headline"]),
            abstract=str(row.get("abstract") or ""),
            url=str(row.get("url") or ""),
        ))
    return out


def merge_source_archives(parts: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate per-source DataFrames into the canonical schema.

    Each `part` must already conform to REQUIRED_COLUMNS.
    Deduplicates on (source, url) — same article re-pulled twice
    is collapsed.
    """
    if not parts:
        return pd.DataFrame(columns=sorted(REQUIRED_COLUMNS))
    frames = []
    for p in parts:
        missing = REQUIRED_COLUMNS - set(p.columns)
        if missing:
            raise NewsArchiveError(
                f"merge: source frame missing columns {missing}"
            )
        frames.append(p[sorted(REQUIRED_COLUMNS)])
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    out = out.drop_duplicates(subset=["source", "url"], keep="first")
    out = out.sort_values("date").reset_index(drop=True)
    return out
