"""Build data/cross_asset.json: factors -> surprises -> per-asset ridge attribution.

All-or-nothing: the file is written atomically and only if every asset fits, so a failed run
leaves the previous week's snapshot in place.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from castelino.cross_asset import consensus, factors, model

NY = ZoneInfo("America/New_York")
CLOSE = time(16, 30)


class NothingToDo(Exception):  # noqa: N818 - an outcome, mapped to refresh.Skipped
    pass


def out_path() -> Path:
    from castelino.config import get_settings

    return get_settings().root / "data" / "cross_asset.json"


def cache_path() -> Path:
    from castelino.config import get_settings

    return get_settings().root / "data" / "cross_asset" / "consensus.json"


def last_completed_friday(now: datetime) -> date:
    local = now.astimezone(NY)
    d = local.date()
    back = (d.weekday() - 4) % 7  # days since the most recent Friday (0 if today is Friday)
    friday = d - timedelta(days=back)
    if back == 0 and local.time() < CLOSE:
        friday -= timedelta(days=7)
    return friday


def _has_key() -> bool:
    from castelino.data.web_search import has_key

    return has_key()


def run(
    now: datetime | None = None,
    *,
    fetch_fred=factors._default_fred,
    fetch_yf=factors._default_yf,
    fetch_cftc=factors.fetch_cftc,
    search=None,
    out: Path | None = None,
    cache: Path | None = None,
    consensus_cap: int | None = 10,
) -> str:
    now = now or datetime.now(UTC)
    out = out or out_path()
    cache = cache or cache_path()
    week_end = last_completed_friday(now)
    if out.exists():
        prev = json.loads(out.read_text())
        # a partial week (a source hadn't posted the week's last day yet) is recomputed later
        if prev.get("week_end") == week_end.isoformat() and not prev.get("partial"):
            raise NothingToDo(f"week ending {week_end} already explained")

    gaps: list[str] = []
    store = consensus.load_cache(cache)
    if search is not None or _has_key():
        consensus.update(
            store,
            now.astimezone(NY).date(),
            search=search or consensus._default_search,
            cap=consensus_cap,
        )
        consensus.save_cache(cache, store)
    else:
        gaps.append("No OPENAI_API_KEY: new release consensus not searched")

    returns = factors.asset_returns(week_end, fetch_yf=fetch_yf)  # StaleAsset -> nothing written
    last_bar = returns.attrs["last_bar"]
    x, fgaps = factors.build_market_factors(
        week_end, fetch_fred, fetch_yf, fetch_cftc, asof=last_bar
    )
    partial = last_bar < pd.Timestamp(week_end) or any(factors.LATE in g for g in fgaps)
    surprises, rows, sgaps = consensus.weekly_surprises(store, x.index)
    x = x.join(surprises)
    gaps += fgaps + sgaps

    assets = {}
    for key, (ticker, name) in factors.ASSETS.items():
        block = model.explain(key, x, returns[key])  # any failure aborts the whole run
        block.update(name=name, ticker=ticker)
        block["summary"] = model.summary_line(block)
        assets[key] = block

    start_3m = pd.Timestamp(week_end) - pd.Timedelta(weeks=13)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "week_end": week_end.isoformat(),
        "partial": partial,
        "assets": assets,
        "surprises": [s for s in rows if pd.Timestamp(s["release_date"]) > start_3m],
        "releases_checked": {
            "ok": sum(v.get("status") == "ok" for v in store.values()),
            "total": len(store),
        },
        "data_gaps": gaps,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, out)
    r2 = ", ".join(
        f"{a['name']} {a['oos_r2']:.0%}" for a in assets.values() if a["oos_r2"] is not None
    )
    return f"week {week_end} explained ({r2 or 'walk-forward R² n/a'}), {len(gaps)} data gaps"
