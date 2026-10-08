"""'As of a past day' data access, for rebuilding old Morning Notes (scripts/backfill_updates.py).

FRED comes from its vintage archive (values as they were known on the day), so a release published
later never leaks in. Prices and Polymarket odds are simply cut off at the day's end.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pandas as pd
import requests

from castelino.agents.update.models import SeriesRef

FRED_OBS = "https://api.stlouisfed.org/fred/series/observations"
WINDOW = 7


def day_end_ts(day: date) -> int:
    return int(datetime.combine(day + timedelta(days=1), time.min, UTC).timestamp()) - 1


def truncate(s: pd.Series, day: date) -> pd.Series:
    return s[s.index <= pd.Timestamp(day)]


def fred_vintage(
    series_id: str, day: date, *, api_key: str | None = None, get=requests.get
) -> pd.Series:
    """The series as FRED published it on `day` (ALFRED vintage). Needs FRED_API_KEY."""
    if api_key is None:
        from castelino.config import get_settings

        api_key = get_settings().fred_api_key
    if not api_key:
        raise RuntimeError("FRED vintages need FRED_API_KEY")
    r = get(
        FRED_OBS,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "realtime_start": day.isoformat(),
            "realtime_end": day.isoformat(),
        },
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json().get("observations", []))
    if df.empty:
        raise RuntimeError(f"FRED had no {series_id} observations as of {day}")
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return (
        df.dropna(subset=["value"])
        .set_index("date")
        .sort_index()["value"]
        .astype(float)
        .rename(series_id)
    )


def _close(ref: SeriesRef) -> pd.Series:
    from castelino.forecast import regime

    fn = regime._fetch_fred_series if ref.provider == "fred" else regime._fetch_yf_close
    return fn(ref.id).dropna()


def chart_fetch(ref: SeriesRef, day: date) -> list[tuple[str, float]]:
    """charts.make_exhibits fetch= for a past day: the last 7 observations up to that day."""
    if ref.provider == "polymarket":
        from castelino.agents.update.sources import polymarket

        end = day_end_ts(day)
        by_day: dict[str, float] = {}
        for t, p in polymarket.price_history(ref.id, start=end - 10 * 86400, end=end):
            by_day[datetime.fromtimestamp(t, UTC).strftime("%b %d")] = p * 100
        return list(by_day.items())[-WINDOW:]
    s = truncate(_close(ref), day).tail(WINDOW)
    return [(pd.Timestamp(i).strftime("%b %d"), float(v)) for i, v in s.items()]
