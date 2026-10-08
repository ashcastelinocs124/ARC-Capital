"""Rebuild past Daily Updates as Morning Notes through the multi-agent desk, as of each day.

    uv run python scripts/backfill_updates.py 2026-09-30 2026-10-01 ...   [--force]

Days run oldest first with a temporary memory, so each note sees only earlier days' themes and the
real memory is untouched. Macro data comes from FRED vintages and prices/odds cut off at the day;
news and X are searched for that date (best effort). Old v1 briefings move to
data/updates/hidden-v1/; if a day fails, its old briefing is put back. Rebuilt records carry
`backfilled: true`, which the page shows.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import date
from functools import partial
from pathlib import Path

from castelino.agents.update import ai, alt, asof, charts, editor, macro, news, orchestrator
from castelino.agents.update.memory import MemoryStore
from castelino.agents.update.runner import UpdateRunner, read_status
from castelino.config import get_settings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("days", nargs="+", type=date.fromisoformat)
    ap.add_argument(
        "--force", action="store_true", help="rebuild days that are already Morning Notes"
    )
    args = ap.parse_args()

    cfg = get_settings()
    ua = cfg.update_agent
    updates = cfg.root / ua.updates_dir
    backup = updates / "hidden-v1"
    backup.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="arc-backfill-"))
    memory = MemoryStore(
        tmp / "memory",
        short_cap=ua.short_term_notes,
        long_cap=ua.long_term_notes,
        refresh_days=ua.long_term_refresh_days,
    )
    failed = 0
    for day in sorted(args.days):
        f = updates / f"{day}.json"
        moved = None
        if f.exists():
            if json.loads(f.read_text()).get("version") == 2 and not args.force:
                print(f"{day}: already a Morning Note, skipped (--force to rebuild)")
                continue
            moved = backup / f.name
            shutil.move(f, moved)

        runner = UpdateRunner(
            data_dir=tmp / "run",
            updates_dir=updates,
            memory=memory,
            max_rounds=0,  # no follow-up rounds: they double a rebuild's time for little gain
            max_retries=ua.max_guard_retries,
            max_items=ua.items,
            plan_fn=orchestrator.plan,
            review_fn=orchestrator.review,
            agent_fns={
                "macro": partial(macro.run, day=day),
                "news": partial(news.run, day=day),
                "alt": partial(alt.run, day=day),
                "ai": partial(ai.run, day=day),
            },
            editor_fn=editor.write_note,
            chart_fn=lambda fs, out, d=day: charts.make_exhibits(
                fs, out, fetch=lambda ref: asof.chart_fetch(ref, d)
            ),
            today_fn=lambda d=day: d,
        )
        result = runner.run_if_due()
        if result == "done":
            rec = json.loads(f.read_text())
            rec["backfilled"] = True
            f.write_text(json.dumps(rec, indent=2))
            words = [len(i["body"].split()) for i in rec["note"]["items"]]
            print(f"{day}: rebuilt — {rec['note']['headline'][:80]} | items {words} words")
        else:
            failed += 1
            if moved is not None:
                shutil.move(moved, f)
            print(f"{day}: {result} — {read_status(tmp / 'run').get('error')}; old briefing kept")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
