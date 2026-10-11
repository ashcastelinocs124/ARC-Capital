"""Which week a deep dive covers, when one is due, and the Morning Notes it reads."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path


def week_id(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(week: str) -> tuple[date, date]:
    y, w = week.split("-W")
    mon = date.fromisocalendar(int(y), int(w), 1)
    return mon, mon + timedelta(days=4)


def due_week(today: date, deep_dir: Path) -> str | None:
    """Sat/Sun → this ISO week; Mon–Fri → last ISO week. None once that report exists."""
    ref = today if today.weekday() >= 5 else today - timedelta(days=7)
    week = week_id(ref)
    return None if (Path(deep_dir) / f"{week}.json").exists() else week


@dataclass
class WeekInputs:
    week: str
    start: date
    end: date
    days: list[str]
    records: list[dict]
    gaps: list[str] = field(default_factory=list)


def load_week(updates_dir: Path, week: str, min_notes: int) -> WeekInputs:
    start, end = week_bounds(week)
    days: list[str] = []
    records: list[dict] = []
    gaps: list[str] = []
    d = start
    while d <= end:
        day = d.isoformat()
        try:
            rec = json.loads((Path(updates_dir) / f"{day}.json").read_text())
        except (OSError, ValueError):
            gaps.append(f"{day}: no Morning Note")
        else:
            if rec.get("version") == 2:
                days.append(day)
                records.append(rec)
            else:
                gaps.append(f"{day}: not a v2 Morning Note")
        d += timedelta(days=1)
    if len(records) < min_notes:
        raise RuntimeError(f"only {len(records)} Morning Notes for {week}; need {min_notes}")
    return WeekInputs(week, start, end, days, records, gaps)


def week_markdown(inp: WeekInputs) -> str:
    out = []
    for day, rec in zip(inp.days, inp.records, strict=True):
        note = rec["note"]
        claims = {f["id"]: f["claim"] for f in rec.get("findings", [])}
        lines = [f"## {day}: {note['headline']}"]
        lines += [f"- takeaway: {t}" for t in note["takeaways"]]
        for it in sorted(note["items"], key=lambda i: i["rank"]):
            lines.append(f"- item {it['rank']}: {it['title']}: {it['body']}")
            lines += [f"  - finding: {claims[f]}" for f in it["finding_ids"] if f in claims]
        out.append("\n".join(lines))
    return "\n\n".join(out)
