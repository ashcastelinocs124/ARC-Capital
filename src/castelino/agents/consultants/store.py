"""Consultant files: data/consultants/<slug>/ (gitignored), one folder per consultant.

  consultant.json   topic, watchlist, status          thesis.json   the two-part thesis
  facts/<day>.json  that day's facts                  history.jsonl one line per daily/weekly review
  days/<day>.json   cost, asks, notes for the day     MEMORY.md / long-term.md   two-tier memory

Two processes write here on Fly (the 17:00 cron run and the admin desk app), so every read-modify-write goes
through `edit()` / `edit_day()`, which hold a cross-process `fcntl.flock` on the folder's lock file. Whole-file
writes (facts, thesis, memory) are atomic and come from one writer at a time, so they don't lock: flock is not
re-entrant, and a writer called inside `edit()` would deadlock."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from castelino.agents.consultants.models import Consultant, DayLog, HistoryLine, Thesis, Watchlist
from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.memory import Note, parse_notes, render_note
from castelino.agents.update.models import Fact
from castelino.config import get_settings

_HIDDEN = "hidden"


def root() -> Path:
    if env := os.environ.get("ARC_CONSULTANTS_DIR", "").strip():
        return Path(env)
    cfg = get_settings()
    return cfg.root / cfg.consultants.data_dir


def cdir(slug: str) -> Path:
    return root() / slug


def _slugify(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40].strip("-") or "topic"


def _count_all() -> int:
    r = root()
    live = [p for p in r.iterdir() if p.is_dir() and p.name != _HIDDEN] if r.exists() else []
    hidden = list((r / _HIDDEN).iterdir()) if (r / _HIDDEN).exists() else []
    return len(live) + len(hidden)


def _save(c: Consultant) -> None:
    atomic_write_text(cdir(c.slug) / "consultant.json", c.model_dump_json(indent=1))


def create(topic: str, watchlist: Watchlist) -> Consultant:
    base = _slugify(topic)
    slug, k = base, 2
    while cdir(slug).exists():
        slug, k = f"{base}-{k}", k + 1
    c = Consultant(
        slug=slug,
        code=f"K{_count_all() + 1}",
        topic=topic.strip(),
        watchlist=watchlist,
        status="building",
        created=date.today().isoformat(),
    )
    _save(c)
    return c


def load(slug: str) -> Consultant:
    p = cdir(slug) / "consultant.json"
    if not slug or "/" in slug or not p.exists():
        raise KeyError(slug)
    return Consultant.model_validate_json(p.read_text())


def all() -> list[Consultant]:  # noqa: A001 - mirrors research store.all()
    r = root()
    if not r.exists():
        return []
    out = []
    for p in r.iterdir():
        try:
            out.append(load(p.name))
        except Exception:  # noqa: BLE001 - not a consultant, unreadable, or deleted mid-listing
            continue
    return sorted(out, key=lambda c: (c.created, c.slug))


def active() -> list[Consultant]:
    return [c for c in all() if c.status != "paused"]


@contextmanager
def lock(slug: str) -> Iterator[None]:
    path = cdir(slug) / "lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        # ponytail: one flock per consultant; fine for a handful of topics
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


@contextmanager
def edit(slug: str) -> Iterator[Consultant]:
    with lock(slug):
        c = load(slug)
        yield c
        _save(c)


def hide(slug: str) -> None:
    load(slug)  # KeyError for an unknown slug
    dest = root() / _HIDDEN / f"{slug}-{datetime.now():%Y%m%d-%H%M%S}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(cdir(slug)), dest)


# ── thesis ──────────────────────────────────────────────────────────────────


def read_thesis(slug: str) -> Thesis | None:
    p = cdir(slug) / "thesis.json"
    return Thesis.model_validate_json(p.read_text()) if p.exists() else None


def write_thesis(slug: str, t: Thesis) -> None:
    atomic_write_text(cdir(slug) / "thesis.json", t.model_dump_json(indent=1))


# ── facts ───────────────────────────────────────────────────────────────────


def read_facts(slug: str, day: str) -> list[Fact]:
    p = cdir(slug) / "facts" / f"{day}.json"
    if not p.exists():
        return []
    return [Fact(**f) for f in json.loads(p.read_text())]


def write_facts(slug: str, day: str, facts: list[Fact]) -> None:
    atomic_write_text(
        cdir(slug) / "facts" / f"{day}.json", json.dumps([f.model_dump() for f in facts], indent=1)
    )


def fact_days(slug: str) -> list[str]:
    """Days that have facts, oldest first."""
    d = cdir(slug) / "facts"
    return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []


def _day_of(fid: str) -> str | None:
    m = re.match(r"^K\d+-(\d{4})(\d{2})(\d{2})-", fid)
    return f"{m[1]}-{m[2]}-{m[3]}" if m else None


def facts_by_id(slug: str, ids: list[str]) -> list[Fact]:
    days: dict[str, dict[str, Fact]] = {}
    out = []
    for fid in ids:
        day = _day_of(fid)
        if day is None:
            continue
        if day not in days:
            days[day] = {f.id: f for f in read_facts(slug, day)}
        if fid in days[day]:
            out.append(days[day][fid])
    return out


def recent_facts(slug: str, days: int, today: date) -> list[Fact]:
    """The last `days` days of facts, oldest first."""
    out: list[Fact] = []
    for k in range(days - 1, -1, -1):
        out += read_facts(slug, (today - timedelta(days=k)).isoformat())
    return out


# a date a build stamps into otherwise unchanged data ("as of Oct 24, 2026", "2026-10-24")
_STAMP = re.compile(r"\b(?:as of )?(?:[A-Z][a-z]{2,8}\.? \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2})")


def fact_key(text: str) -> str:
    """A fact's text without stamped dates, so the same data gathered on two days compares equal.
    ponytail: exact text otherwise; a search that words an old story anew still counts as new (the post
    question and the Post Writer see the posts already out for that)."""
    return _STAMP.sub("", text)


def earlier_texts(slug: str, day: str, days: int = 7) -> dict[str, str]:
    """fact_key -> the first of the `days` days before `day` it was gathered. A build fetches some data
    again unchanged (a monthly index re-read every day), so a fact found here is not news on `day`."""
    out: dict[str, str] = {}
    for f in recent_facts(slug, days, date.fromisoformat(day) - timedelta(days=1)):  # oldest first
        out.setdefault(fact_key(f.text), _day_of(f.id) or "")
    return out


# ── history and day logs ────────────────────────────────────────────────────


def append_history(slug: str, line: HistoryLine) -> None:
    p = cdir(slug) / "history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:  # O_APPEND: one short line, never interleaved
        fh.write(line.model_dump_json() + "\n")


def history(slug: str) -> list[HistoryLine]:
    p = cdir(slug) / "history.jsonl"
    if not p.exists():
        return []
    return [HistoryLine.model_validate_json(x) for x in p.read_text().splitlines() if x.strip()]


def posts_md(slug: str, n: int = 5) -> str:
    """The last `n` posts, one "- day: text [chart: …]" line each, so a new post can be told apart from them."""
    lines = [
        f"- {h.day}: {h.post}"
        + (f" [chart: {h.chart_form} of {', '.join(h.chart_series)}]" if h.chart_series else "")
        for h in recent_posts(slug, n)
    ]
    return "\n".join(lines) or "(none)"


def recent_posts(slug: str, n: int = 5) -> list[HistoryLine]:
    return [h for h in history(slug) if h.post][-n:]


def day_log(slug: str, day: str) -> DayLog:
    p = cdir(slug) / "days" / f"{day}.json"
    return DayLog.model_validate_json(p.read_text()) if p.exists() else DayLog(day=day)


@contextmanager
def edit_day(slug: str, day: str) -> Iterator[DayLog]:
    with lock(slug):
        d = day_log(slug, day)
        yield d
        atomic_write_text(cdir(slug) / "days" / f"{day}.json", d.model_dump_json(indent=1))


# ── memory (the repo's two-tier note format) ────────────────────────────────


def _read_notes(path: Path) -> list[Note]:
    return parse_notes(path.read_text()) if path.exists() else []


def read_memory(slug: str) -> tuple[list[Note], list[Note]]:
    d = cdir(slug)
    return _read_notes(d / "MEMORY.md"), _read_notes(d / "long-term.md")


def memory_md(notes: list[Note], title: str) -> str:
    return f"# {title}\n\n## Notes\n" + "\n".join(render_note(n) for n in notes)


def write_memory(slug: str, short: list[Note], long: list[Note]) -> None:
    d = cdir(slug)
    atomic_write_text(d / "MEMORY.md", memory_md(short, "Short-term memory (this week)"))
    atomic_write_text(d / "long-term.md", memory_md(long, "Long-term memory"))
