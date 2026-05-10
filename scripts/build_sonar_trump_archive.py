"""Build the Trump-events half of `historical_news.parquet` via Perplexity Sonar.

NYT undercounts political/policy chatter that drives markets — tariff
threats, executive orders, social-media policy posts, SCOTUS-related
remarks. Sonar is a web-search-with-citations API; we ask it once per
month for the most market-moving Trump-related events in that month
and store the structured result.

Cost: ~30 months × ~$0.05 = $1.50 total (vs. hundreds of NYT calls).

Schema:
    date     : pd.Timestamp
    source   : "sonar_trump"
    headline : str
    abstract : str
    url      : str    (Sonar source URL)

Usage:
    python scripts/build_sonar_trump_archive.py
    python scripts/build_sonar_trump_archive.py --start 2023-10 --end 2026-05
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from castelino.backtest.news_archive import (  # noqa: E402
    REQUIRED_COLUMNS,
    historical_news_path,
    merge_source_archives,
)
from castelino.config import get_settings  # noqa: E402

log = logging.getLogger("build_sonar_trump_archive")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


_PROMPT = """\
List the {max_items} most market-moving events involving Donald Trump in
{month_label} ({year}-{month:02d}). Cover any of: tariff announcements,
executive orders, statements about the Federal Reserve or interest rates,
trade-policy threats, regulatory actions, geopolitical remarks, major
campaign or court events that moved equity / bond / FX markets.

For EACH event return a JSON object with these EXACT keys:
  - "date": ISO 8601 date (YYYY-MM-DD) of the event itself
  - "headline": short factual headline (≤ 200 chars)
  - "abstract": 1-2 sentence summary of what happened and the market context
  - "url": canonical source URL (a real article you used)

Rules:
- Stay grounded in real published sources. Do NOT invent events.
- If fewer than {max_items} truly notable events exist that month, return
  fewer rather than padding.
- Return ONLY a JSON array. No prefatory text, no markdown fences.
"""


_FENCE_RX = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _parse_response(raw: str) -> list[dict]:
    text = raw.strip()
    m = _FENCE_RX.search(text)
    if m:
        text = m.group(1).strip()
    s, e = text.find("["), text.rfind("]")
    if s == -1 or e == -1:
        raise ValueError(f"no JSON array in Sonar response: {raw[:200]!r}")
    return json.loads(text[s : e + 1])


def _months_between(start: date, end: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _query_month(client: OpenAI, year: int, month: int, max_items: int, model: str) -> list[dict]:
    prompt = _PROMPT.format(
        month_label=_MONTH_NAMES[month - 1],
        year=year, month=month, max_items=max_items,
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a research assistant who finds and "
                        "summarizes real published events. Stay grounded "
                        "in actual sources you can cite. Return JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as e:
        log.warning("Sonar Trump %s/%02d call failed: %s", year, month, e)
        return []
    raw = (resp.choices[0].message.content or "").strip()
    try:
        items = _parse_response(raw)
    except Exception as e:
        log.warning("Sonar Trump %s/%02d parse failed: %s", year, month, e)
        return []

    rows: list[dict] = []
    for it in items:
        try:
            d = datetime.fromisoformat(str(it["date"])[:10]).replace(tzinfo=UTC)
        except Exception:
            continue
        # Reject rows clearly outside the requested month
        if d.year != year or d.month != month:
            continue
        rows.append({
            "date": pd.Timestamp(d).tz_localize(None),
            "source": "sonar_trump",
            "headline": str(it.get("headline", ""))[:500],
            "abstract": str(it.get("abstract", ""))[:1000],
            "url": str(it.get("url") or f"sonar://trump/{year}-{month:02d}/{len(rows)}"),
        })
    return rows


def build(start: date, end: date) -> Path:
    cfg = get_settings()
    if not cfg.backtest.sonar_trump_enabled:
        raise SystemExit("backtest.sonar_trump_enabled = false; nothing to do")

    api_key = cfg.perplexity_api_key
    if not api_key:
        raise SystemExit(
            "PERPLEXITY_API_KEY is not set. Add it to .env, then re-run.\n"
            "(Persona system already uses this key; cost for backtest "
            "Trump archive is ~$1.50 over 30 months.)"
        )

    client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
    months = _months_between(start, end)
    max_items = cfg.backtest.sonar_trump_max_per_month
    model = cfg.sonar.model

    log.info("Sonar Trump pull: %d months × ≤%d items each", len(months), max_items)

    rows: list[dict] = []
    for (y, m) in months:
        log.info("Sonar Trump %s/%02d", y, m)
        rows.extend(_query_month(client, y, m, max_items, model))

    if not rows:
        raise SystemExit("Sonar returned zero usable rows — check key / model / network")

    df = pd.DataFrame(rows)[sorted(REQUIRED_COLUMNS)]
    df = df.drop_duplicates(subset=["source", "url"], keep="first")
    log.info("Sonar Trump rows after dedup: %d", len(df))

    out_path = historical_news_path()
    parts = [df]
    if out_path.exists():
        parts.append(pd.read_parquet(out_path))
    merged = merge_source_archives(parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(out_path)
    log.info("wrote %d total rows to %s", len(merged), out_path)
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
