from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.models import DailyUpdate, MarketSnapshot

NOTE_RE = re.compile(
    r"^### (?P<title>.+?) · imp:(?P<imp>[1-5]) · last-used:(?P<date>\d{4}-\d{2}-\d{2})"
    r" · type:(?P<type>\w+)\s*$")
_MARK = re.compile(r"<!-- long-term-table-refreshed: (\d{4}-\d{2}-\d{2}) -->")
_TABLE = re.compile(r"## Long-term trend\n(.*?)\n\n## Notes", re.S)


@dataclass
class Note:
    title: str
    text: str
    importance: int
    last_used: date
    type: str = "theme"


def parse_notes(md: str) -> list[Note]:
    notes: list[Note] = []
    cur: Note | None = None
    body: list[str] = []
    in_notes = False

    def flush() -> None:
        if cur is not None:
            cur.text = "\n".join(body).strip()
            notes.append(cur)

    for line in md.splitlines():
        if line.startswith("## Notes"):
            in_notes = True
            continue
        if not in_notes:
            continue
        m = NOTE_RE.match(line)
        if m:
            flush()
            body = []
            cur = Note(m["title"], "", int(m["imp"]), date.fromisoformat(m["date"]), m["type"])
        elif cur is not None and not line.startswith("### "):
            body.append(line)
        elif line.startswith("### "):      # malformed header: drop it and its body
            flush()
            cur, body = None, []
    flush()
    return notes


def render_note(n: Note) -> str:
    text = re.sub(r"(?m)^#+\s*", "", n.text.strip())   # body can never forge a header
    return (f"### {n.title} · imp:{n.importance} · last-used:{n.last_used.isoformat()}"
            f" · type:{n.type}\n{text}\n")


def relevance(n: Note, today: date) -> int:
    return n.importance - (today - n.last_used).days // 30


def _key(n: Note) -> tuple[int, int]:
    return (-n.importance, -n.last_used.toordinal())


def rebalance(notes: list[Note], today: date, short_cap: int,
              long_cap: int) -> tuple[list[Note], list[Note]]:
    ranked = sorted(notes, key=_key)
    short, rest = ranked[:short_cap], ranked[short_cap:]
    if len(rest) > long_cap:
        drop = sorted(rest, key=lambda n: (relevance(n, today), n.last_used.toordinal()))
        gone = {id(n) for n in drop[: len(rest) - long_cap]}
        rest = [n for n in rest if id(n) not in gone]
    return short, rest


def _f(x: float | None, unit: str = "%") -> str:
    return "n/a" if x is None else f"{x:+.1f}{unit}"


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ").strip()


def short_table(snapshot: MarketSnapshot, reads: dict[str, str]) -> str:
    rows = ["| Sector | 1w | 1m | rel 1m | Trend | Read |", "|---|---|---|---|---|---|"]
    for s in snapshot.sectors:
        rows.append(f"| {s.sector} | {_f(s.r1w)} | {_f(s.r1m)} | {_f(s.rel1m, 'pp')} |"
                    f" {s.short_label} | {_cell(reads.get(s.sector.upper(), ''))} |")
    if not snapshot.sectors:
        rows.append("| no sector data | | | | | |")
    return "\n".join(rows)


def long_table(snapshot: MarketSnapshot) -> str:
    rows = ["| Sector | 3m | 6m | 12m | rel 12m | Structural trend |", "|---|---|---|---|---|---|"]
    for s in snapshot.sectors:
        rows.append(f"| {s.sector} | {_f(s.r3m)} | {_f(s.r6m)} | {_f(s.r12m)} |"
                    f" {_f(s.rel12m, 'pp')} | {s.long_label} |")
    if not snapshot.sectors:
        rows.append("| no sector data | | | | | |")
    return "\n".join(rows)


class MemoryStore:
    """Two-tier markdown memory. Caps, eviction and tables are all code, not prompt."""

    def __init__(self, root: Path, *, short_cap: int = 5, long_cap: int = 20,
                 refresh_days: int = 7):
        self.root = Path(root)
        self.short_cap, self.long_cap, self.refresh_days = short_cap, long_cap, refresh_days

    @property
    def short_path(self) -> Path:
        return self.root / "MEMORY.md"

    @property
    def long_path(self) -> Path:
        return self.root / "long-term.md"

    def read_short(self) -> str:
        return self.short_path.read_text() if self.short_path.is_file() else ""

    def read_long(self) -> str:
        return self.long_path.read_text() if self.long_path.is_file() else ""

    def _long_table_block(self, old_md: str, snapshot: MarketSnapshot,
                          today: date) -> tuple[str, str]:
        m, t = _MARK.search(old_md), _TABLE.search(old_md)
        if m and t and (today - date.fromisoformat(m.group(1))).days < self.refresh_days:
            return m.group(1), t.group(1)
        return today.isoformat(), long_table(snapshot)

    def apply(self, update: DailyUpdate, snapshot: MarketSnapshot, today: date) -> None:
        old_long = self.read_long()
        notes = {n.title.lower(): n for n in parse_notes(self.read_short()) + parse_notes(old_long)}
        for t in update.themes_touched:
            n = notes.get(t.title.lower())
            if n:
                n.text, n.last_used = t.text, today
            else:   # the model named a theme we don't have: treat as a new mid-importance note
                notes[t.title.lower()] = Note(t.title, t.text, 3, today)
        for t in update.new_themes:
            n = notes.get(t.title.lower())
            if n:
                n.text, n.last_used = t.text, today
            else:
                notes[t.title.lower()] = Note(t.title, t.text, t.importance, today)

        short, long = rebalance(list(notes.values()), today, self.short_cap, self.long_cap)
        reads = {r.sector.upper(): r.text for r in update.sector_reads}

        atomic_write_text(self.short_path, (
            "# Update Agent Memory — Short-Term\n"
            f"## Short-term trend (refreshed {today.isoformat()})\n"
            f"{short_table(snapshot, reads)}\n\n## Notes\n"
            + "\n".join(render_note(n) for n in short)))
        marked, table = self._long_table_block(old_long, snapshot, today)
        atomic_write_text(self.long_path, (
            "# Update Agent Memory — Long-Term\n"
            f"<!-- long-term-table-refreshed: {marked} -->\n"
            f"## Long-term trend\n{table}\n\n## Notes\n"
            + "\n".join(render_note(n) for n in long)))
