"""One-time: search 24 months of release consensus for the Cross-Asset model (~120 cited searches).

Usage: uv run python scripts/backfill_consensus.py [--months 24]
Resumable: cached releases are skipped, so rerun after a network drop.
"""

from __future__ import annotations

import argparse
from datetime import date

from castelino.cross_asset import consensus
from castelino.cross_asset.run import cache_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=24)
    a = ap.parse_args()
    today = date.today()
    y, m = divmod(today.year * 12 + today.month - 1 - a.months, 12)
    path = cache_path()
    store = consensus.load_cache(path)
    total = 0
    seen: set[str] = set()  # each release is searched at most once per backfill run
    while True:  # save after every batch of 5 so a crash loses little
        n = consensus.update(store, today, cap=5, start=date(y, m + 1, 1), seen=seen)
        consensus.save_cache(path, store)
        total += n
        ok = sum(v.get("status") == "ok" for v in store.values())
        print(f"[backfill] {total} searches, {ok}/{len(store)} releases verified", flush=True)
        if n == 0:
            break


if __name__ == "__main__":
    main()
