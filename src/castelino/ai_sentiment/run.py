"""Builds data/ai_sentiment.json: one scored day per Refresh, a 14-day backfill on the first run.

Each day: Grok X Search over the tracked accounts (groups of 20 handles) -> post links ->
X oEmbed text -> word-list score per provider. Missing days in the last 14 are filled; today
is always refetched. A day where every group failed is not written.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from castelino.ai_sentiment import scan, score

log = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
GROUP = 20  # x_search takes at most 20 allowed_x_handles
BACKFILL = 14  # rate of change needs two weeks
KEEP_DAYS = 180
SERIES_DAYS = 60
QS = re.compile(r"\?\S*")


class NotConfigured(Exception):  # noqa: N818 - an outcome, mapped to refresh.Skipped
    pass


def has_key() -> bool:
    return scan.has_key()


def _data_dir() -> Path:
    from castelino.config import get_settings

    return get_settings().root / "data" / "ai_sentiment"


def out_path() -> Path:
    from castelino.config import get_settings

    return get_settings().root / "data" / "ai_sentiment.json"


def load_accounts(path: Path) -> dict[str, str]:
    """handle (lower case) -> lab affiliation ('' if independent)."""
    with path.open() as f:
        return {r["handle"].strip().lower(): r["affiliation"].strip() for r in csv.DictReader(f)}


def load_lexicon(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text())


def _write(out: Path, data: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, out)


def providers(days: dict[str, dict], today: date) -> dict[str, dict]:
    fams = sorted({f for d in days.values() for f in d})
    last7 = {(today - timedelta(days=k)).isoformat() for k in range(7)}
    out = {}
    for fam in fams:
        ser = score.series(days, fam)
        latest = max(d for d in days if fam in days[d])
        out[fam] = {
            "level": ser[-1][1] if ser else days[latest][fam]["net"],
            "delta": score.delta(ser),
            "n7": sum(days[d][fam]["n"] for d in days if d in last7 and fam in days[d]),
            "series": [list(p) for p in ser[-SERIES_DAYS:]],
            "samples": days[latest][fam]["samples"],
        }
    return out


def run(
    now: datetime | None = None,
    *,
    out: Path | None = None,
    accounts: dict[str, str] | None = None,
    lex: dict | None = None,
    find=None,
    fetch=None,
    has_key=None,
) -> str:
    if not (has_key or globals()["has_key"])():
        raise NotConfigured("XAI_API_KEY not set")
    now = now or datetime.now(UTC)
    out = out or out_path()
    accounts = accounts or load_accounts(_data_dir() / "accounts.csv")
    lex = lex or load_lexicon(_data_dir() / "lexicon.yaml")
    find = find or scan.find_posts
    fetch = fetch or scan.fetch_posts

    prev = json.loads(out.read_text()) if out.exists() else {}
    days: dict[str, dict] = prev.get("days") or {}
    today = now.astimezone(NY).date()
    window = [today - timedelta(days=k) for k in range(BACKFILL - 1, -1, -1)]
    todo = [d for d in window if d.isoformat() not in days or d == today]
    handles = sorted(accounts)
    groups = [handles[i : i + GROUP] for i in range(0, len(handles), GROUP)]
    gaps: list[dict] = []

    for d in todo:
        urls: list[str] = []
        ok = 0
        for g in groups:
            try:
                urls += [u for u in find(g, d) if u not in urls]
                ok += 1
            except Exception as e:  # noqa: BLE001 - one group never loses the day
                msg = QS.sub("", str(e))[:200]
                log.warning("ai_sentiment %s group: %s", d, msg)
                gaps.append({"day": d.isoformat(), "error": msg})
        if not ok:
            continue  # nothing fetched: keep whatever we had for that day
        days[d.isoformat()] = score.daily(fetch(urls, accounts), accounts, lex)

    keep = sorted(days)[-KEEP_DAYS:]
    days = {k: days[k] for k in keep}
    _write(
        out,
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "accounts": len(accounts),
            "days": days,
            "providers": providers(days, today) if days else {},
            "gaps": gaps,
        },
    )
    return f"{len(todo)} day(s) scored, {len(gaps)} gap(s)"
