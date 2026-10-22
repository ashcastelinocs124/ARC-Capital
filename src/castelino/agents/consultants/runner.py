"""When consultants work: inside the Daily Update's Refresh job (Fly's 17:00 ET run).

  before_note(day)  build every active consultant (parallel)       → the Daily Update reads their theses
  after_note(day)   evening review of each; Sunday's weekly memory review (a missed Sunday is caught up
                    first on the next run, before that day's review adds a new short-term note)
  submit_start(slug) the first build, right after Start in /admin → Consultants

Every step is checked against the consultant's daily cost cap first and adds what it spent; a failure is
a note in that day's log, never an exception: consultants are never load-bearing for the Daily Update."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import TypeVar

from castelino.agents.consultants import build, review, store
from castelino.agents.consultants.models import HistoryLine
from castelino.agents.trade import llm
from castelino.agents.update.models import DailyRecordV2
from castelino.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T")
# rough $ per step, checked against cost_cap_usd before it runs; review includes a possible rewrite
EST = {"build": 0.50, "review": 0.15, "weekly": 0.05}


def charge(slug: str, day: str, step: str) -> bool:
    cap = get_settings().consultants.cost_cap_usd
    with store.edit_day(slug, day) as d:
        if d.cost_usd + EST[step] > cap:
            d.notes.append(
                f"cost cap: skipped {step} (${d.cost_usd:.2f} spent today; cap ${cap:.2f})"
            )
            return False
    return True


def run_step(slug: str, day: str, step: str, fn: Callable[[llm.Meter], T]) -> T | None:
    if not charge(slug, day, step):
        return None
    meter = llm.Meter()
    try:
        return fn(meter)
    except Exception as e:  # noqa: BLE001 - logged in the day's notes, never raised
        log.warning("consultant %s: %s failed", slug, step, exc_info=True)
        with store.edit_day(slug, day) as d:
            d.notes.append(f"{step} failed: {str(e)[:200]}")
        return None
    finally:
        if meter.total:
            with store.edit_day(slug, day) as d:
                d.cost_usd += meter.total


def before_note(day: date) -> list[str]:
    """Build every active consultant for `day`. Returns their gaps; never raises."""
    if not get_settings().consultants.enabled:
        return []
    ds = day.isoformat()
    try:
        cs = store.active()

        def one(c) -> list[str]:
            return run_step(c.slug, ds, "build", lambda m: build.build(c.slug, day, m)) or []

        with ThreadPoolExecutor(4) as ex:
            done = zip(cs, ex.map(one, cs), strict=True)
            return [f"{c.topic}: {g}" for c, gaps in done for g in gaps]
    except Exception:  # noqa: BLE001
        log.warning("consultants: build step failed", exc_info=True)
        return []


def after_note(day: date, updates_dir: Path) -> None:
    """Evening review (and Sunday's weekly review) for every active consultant; never raises."""
    if not get_settings().consultants.enabled:
        return
    ds, we = day.isoformat(), review.last_sunday(day)
    try:
        path = Path(updates_dir) / f"{ds}.json"
        findings = (
            DailyRecordV2.model_validate_json(path.read_text()).findings if path.exists() else None
        )
        cs = store.active()
    except Exception:  # noqa: BLE001
        log.warning("consultants: could not read today's note", exc_info=True)
        return
    for c in cs:
        try:
            if day != we:  # catch up a missed Sunday before today adds a new short-term note
                run_step(c.slug, ds, "weekly", lambda m, s=c.slug: review.weekly(s, we, m))
            if findings is not None:
                run_step(c.slug, ds, "review", lambda m, s=c.slug: review.daily(s, ds, findings, m))
            elif not any(h.day == ds and h.kind == "daily" for h in store.history(c.slug)):
                store.append_history(
                    c.slug,
                    HistoryLine(
                        day=ds, kind="daily", verdict="skipped", reason="No Daily Update today."
                    ),
                )
            if day == we:
                run_step(c.slug, ds, "weekly", lambda m, s=c.slug: review.weekly(s, we, m))
        except Exception:  # noqa: BLE001
            log.warning("consultant %s: review failed", c.slug, exc_info=True)


def submit_start(slug: str) -> None:
    """The first build, in the background, right after Start (also the tab's Build now retry)."""

    def go() -> None:
        today = date.today()
        run_step(slug, today.isoformat(), "build", lambda m: build.build(slug, today, m))

    threading.Thread(target=go, daemon=True, name=f"consultant-{slug}-start").start()
