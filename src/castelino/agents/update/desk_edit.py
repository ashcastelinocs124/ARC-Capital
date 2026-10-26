"""Admin Daily desk: edit a day's note, by asking the Editor or by hand.

Ask: the Edit Router decides whether a request changes what the note says or adds a new point.
A new point the day's findings don't cover is researched first by the one analyst that covers it
(a mini run, `desk.rerun_locked`). The Editor then rewrites the note with the request, through
the usual guard and charts, into a PROPOSAL under updates/proposals/<day>/: the record is not
touched until the editor approves it on the desk. By hand: the desk sends the edited text and
where each chart sits; the guard's number check only warns, because the editor is the author.

Everything that rewrites the record backs it up first and runs under the day's lock.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.agents.update import desk
from castelino.agents.update.fsio import acquire_lock, atomic_write_text, release_lock
from castelino.agents.update.guard import check_note
from castelino.agents.update.models import DailyRecordV2, Exhibit, Fact, Finding, MorningNote
from castelino.config import get_settings

NAMES = {
    "macro": "Macro analyst",
    "news": "News analyst",
    "alt": "Alt data analyst",
    "ai": "AI analyst",
}
_PARAS = re.compile(r"\n\s*\n")


class StaleProposalError(RuntimeError):
    """The note changed after the draft was made, so approving it would undo that change."""


# ── the router ─────────────────────────────────────────────────────────────


class EditRoute(BaseModel):  # LLM output (closed schema: no defaults)
    kind: Literal["change", "new"]
    items: list[int]
    top: bool
    finding_ids: list[str]
    agent: Literal["macro", "news", "alt", "ai", "none"]
    brief: str
    reason: str


ROUTER_SYSTEM = """You route an editor's request about one day of ARC Research's Daily Update, a
note with a headline, 3 takeaways and exactly 5 ranked items. Decide:
- kind "change": the request changes what the note already says (rewrite, shorten, re-angle,
  fix, reorder, merge or cut items; the headline or takeaways). items = the ranks it is about:
  all of them for a request about the whole note, [] when it is only about the headline or
  takeaways.
- top: true when the request changes the headline or the takeaways (asks for it, or adds a point
  the editor wants in them), else false.
- kind "new": the request adds a point the note doesn't make. finding_ids = the day's findings
  below that already support it (copy their ids exactly; [] if none do). If they don't cover it,
  set agent to the analyst who covers that kind of story: macro (economic data, rates, FX,
  commodities), news (companies, earnings, policy, markets), alt (prediction markets, posts on
  X), ai (AI models, chips and the AI industry); and brief = what that analyst should find, in
  one or two sentences that name the day. Otherwise agent "none" and brief "".
- reason: one plain sentence to the editor, in the first person, saying what you will do and
  why ("This adds a point the note doesn't make, so I'm asking the News analyst for sources.")."""


class EditRouter(StructuredAgent[EditRoute]):
    name = "desk_edit"
    output_schema = EditRoute
    tier = "fast"

    def __init__(self) -> None:
        cfg = get_settings().update_agent
        self.model = cfg.agent_model
        self.max_output_tokens = cfg.max_output_tokens  # luna reasons first

    def system_prompt(self) -> str:
        return ROUTER_SYSTEM

    def user_prompt(self, *, day: str, ask: str, note_md: str, findings_md: str) -> str:
        return (
            f"Day: {day}\n\n## The note\n{note_md}\n\n## The day's findings\n{findings_md}"
            f"\n\n## The editor's request\n{ask}"
        )


def note_md(note: MorningNote) -> str:
    lines = [f"Headline: {note.headline}", "Takeaways:", *(f"- {t}" for t in note.takeaways)]
    lines += [
        f"Item {it.rank}: {it.title} (findings {', '.join(it.finding_ids)})"
        for it in sorted(note.items, key=lambda i: i.rank)
    ]
    return "\n".join(lines)


def request_md(ask: str, route: EditRoute, note: MorningNote, new_ids: list[str]) -> str:
    """What the Editor is asked to do, with the current note to copy from."""
    keep = (
        "Keep everything the request doesn't touch exactly as it is: copy every other item's "
        "title, body, finding_ids, chart, exhibit and view word for word, and the headline and "
        "takeaways, unless the request is about them."
    )
    if route.kind == "new":
        task = (
            f"Add this as a new item resting on findings {', '.join(new_ids)}. Rank it among the "
            f"items by importance and drop the weakest item so there are still exactly "
            f"{len(note.items)}; re-rank the rest in order. {keep} Change a takeaway or the "
            "headline only if the new point changes the day's story."
        )
    else:
        about = f" It is about item(s) {', '.join(map(str, route.items))}." if route.items else ""
        task = f"Make this change.{about} {keep}"
    return (
        f'The desk editor asked: "{ask}"\n\n{task}\n\nThe current note (the same shape you '
        f"return):\n{note.model_dump_json(indent=1)}"
    )


def keep_untouched(
    old: MorningNote, route: EditRoute, new_ids: list[str] = ()
) -> Callable[[MorningNote], MorningNote]:
    """Put back, word for word, what the request isn't about: the Editor rewrites the whole note
    and rewords items it was told to keep. Each draft item is matched to the current one with the
    same title, else the one sharing most of its findings; a matched item outside `route.items`
    gets its current text, findings, chart pick and view back (its rank can still move, e.g. under
    a new point). An item citing the new point's findings (`new_ids`) is always the Editor's.
    The headline and takeaways change only when the request is about them."""
    touched = set(route.items) if route.kind == "change" else set()
    if route.kind == "change" and not touched and not route.top:
        touched = {it.rank for it in old.items}  # unsure what it's about: trust the Editor

    def match(it, pool):
        same = [o for o in pool if o.title == it.title]
        if same:
            return same[0]
        overlap = [(len(set(o.finding_ids) & set(it.finding_ids)), o) for o in pool]
        n, best = max(overlap, key=lambda x: x[0], default=(0, None))
        return best if n and n * 2 >= len(set(it.finding_ids) | set(best.finding_ids)) else None

    def merge(new: MorningNote) -> MorningNote:
        pool, items = list(old.items), []
        for it in new.items:
            o = None if set(it.finding_ids) & set(new_ids) else match(it, pool)
            if o is not None:
                pool.remove(o)
                if o.rank not in touched:
                    it = o.model_copy(update={"rank": it.rank})
            items.append(it)
        top = {} if route.top else {"headline": old.headline, "takeaways": old.takeaways}
        return new.model_copy(update={"items": items, **top})

    return merge


# ── charts: where they sit, and their numbers ──────────────────────────────


def n_paras(body: str) -> int:
    return len([p for p in _PARAS.split(body) if p.strip()])


def reading_order(note: MorningNote, exhibits: list[Exhibit]) -> list[Exhibit]:
    """The charts in the order a reader meets them (substack.chart_slots places them the same way)."""
    paras = {it.rank: n_paras(it.body) for it in note.items}

    def key(e: Exhibit) -> tuple[int, int, int]:
        host = e.at or e.item or 0
        end = paras.get(host, 0)
        return host, end if e.after is None else min(e.after, end), e.n

    return sorted(exhibits, key=key)


def renumber(
    note: MorningNote,
    exhibits: list[Exhibit],
    findings: list[Finding],
    facts: list[Fact],
    charts_dir: Path,
    chart_fn: Callable | None = None,
) -> tuple[list[Exhibit], bool]:
    """When a move put the charts out of order, redraw them numbered in reading order (the number
    is drawn into each image) and keep where each one sits. Returns (exhibits, redrawn)."""
    order = reading_order(note, exhibits)
    if [e.n for e in order] == sorted(e.n for e in exhibits):
        return exhibits, False
    if chart_fn is None:
        from castelino.agents.update.exhibits import make_note_exhibits as chart_fn
    place = {e.item: (e.at, e.after) for e in exhibits}
    # ponytail: a line chart re-reads its series, so it can pick up a newer point than first drawn
    new = chart_fn(note, findings, facts, charts_dir, order=[e.item for e in order])
    out = [
        e.model_copy(
            update=dict(zip(("at", "after"), place.get(e.item, (None, None)), strict=True))
        )
        for e in new
    ]
    return out, True


def carry_layout(old: DailyRecordV2, note: MorningNote, exhibits: list[Exhibit]) -> list[Exhibit]:
    """Keep where the desk put a chart when its item, and the item it sat in, survive an edit
    (matched by title, since ranks can shift)."""
    title = {it.rank: it.title for it in old.note.items}
    rank = {it.title: it.rank for it in note.items}
    moved = {
        title.get(e.item): (title.get(e.at or e.item), e.after)
        for e in old.exhibits
        if e.item is not None and (e.at is not None or e.after is not None)
    }
    src = {it.rank: it.title for it in note.items}
    out = []
    for e in exhibits:
        if (m := moved.get(src.get(e.item or 0))) and (host := rank.get(m[0])) is not None:
            e = e.model_copy(update={"at": None if host == e.item else host, "after": m[1]})
        out.append(e)
    return out


# ── what changed (for the chat) ────────────────────────────────────────────


def summarize(old: MorningNote, new: MorningNote) -> dict:
    was = {it.title: it for it in old.items}
    now = {it.title for it in new.items}
    out = {
        "added": [it.rank for it in new.items if it.title not in was],
        "dropped": [it.title for it in old.items if it.title not in now],
        "changed": [
            it.rank for it in new.items if it.title in was and was[it.title].body != it.body
        ],
        "takeaways": sum(a != b for a, b in zip(old.takeaways, new.takeaways, strict=False)),
        "headline": old.headline != new.headline,
    }
    parts = []
    if out["added"]:
        parts.append(f"Your point is item {', '.join(map(str, out['added']))}.")
    if out["dropped"]:
        parts.append("Dropped: " + "; ".join(f"“{t}”" for t in out["dropped"]) + ".")
    if out["changed"]:
        n = out["changed"]
        parts.append(f"Item{'s' if len(n) > 1 else ''} {', '.join(map(str, n))} rewritten.")
    if out["headline"]:
        parts.append("New headline.")
    if out["takeaways"]:
        parts.append(f"{out['takeaways']} takeaway{'s' if out['takeaways'] > 1 else ''} changed.")
    out["text"] = " ".join(parts) or "No visible change: the draft matches the current note."
    return out


# ── proposals ──────────────────────────────────────────────────────────────


def _pdir(day: str) -> Path:
    return desk._dirs()[1] / "proposals" / day


def _hash(updates_dir: Path, day: str) -> str:
    """The record as it was when a draft was made: any later write (re-run, rebuild, a hand
    edit, another approval) changes it, and the draft is then stale."""
    return hashlib.sha256((updates_dir / f"{day}.json").read_bytes()).hexdigest()[:16]


def proposal(day: str) -> dict | None:
    """The pending draft for `day` (meta + record), or None."""
    p = _pdir(day)
    if not (p / "meta.json").exists():
        return None
    meta = json.loads((p / "meta.json").read_text())
    rec = json.loads((p / "record.json").read_text())
    return {**meta, "note": rec["note"], "exhibits": rec["exhibits"], "calendar": rec["calendar"]}


def _locked(fn):
    def wrapper(day: str, *a, **k):
        data_dir, _ = desk._dirs()
        if not acquire_lock(data_dir, desk._LOCK_SECONDS):
            raise RuntimeError("another run is using the day's files; try again in a few minutes")
        try:
            return fn(day, *a, **k)
        finally:
            release_lock(data_dir)

    return wrapper


@_locked
def edit(day: str, ask: str, progress: Callable[[str], None] = lambda s: None) -> dict:
    """Route the request, research a new point if needed, and write the Editor's draft as a
    proposal. Returns what happened for the chat ({kind, agent, added, summary, message})."""
    from castelino.agents.update.runner import build_default_runner

    _, updates_dir = desk._dirs()
    record, _facts = desk.load_day(updates_dir, day)
    progress("Reading your request against the note and the day's findings")
    route = EditRouter()(
        day=day,
        ask=ask,
        note_md=note_md(record.note),
        findings_md="\n".join(f"[{f.id}] ({f.agent}) {f.claim}" for f in record.findings),
    )
    known = {f.id for f in record.findings}
    new_ids = [i for i in route.finding_ids if i in known] if route.kind == "new" else []
    out: dict = {"kind": route.kind, "reason": route.reason, "agent": None, "added": []}
    progress(route.reason)
    if route.kind == "new" and not new_ids:
        agent = route.agent if route.agent in desk.AGENTS else "news"
        out["agent"] = agent
        progress(f"{NAMES[agent]} is researching: {route.brief or ask}")
        added = desk.rerun_locked(day, agent, route.brief or ask)
        record, _facts = desk.load_day(updates_dir, day)
        new_ids = [f.id for f in record.findings if f.id not in known]
        out["added"] = new_ids
        if not added:
            msg = (
                f"The {NAMES[agent]} found nothing sourced on this for {day}, so I haven't "
                "changed anything. If you have a link or a more specific detail, send it and "
                "I'll try again."
            )
            progress(f"{NAMES[agent]} found no sourced reports")
            return out | {"kind": "none", "message": msg}
        progress(f"{NAMES[agent]} came back with {added} sourced point(s): {', '.join(new_ids)}")
    progress("Drafting the note with your request")
    base = _hash(updates_dir, day)
    p = _pdir(day)
    shutil.rmtree(p, ignore_errors=True)  # a new request replaces any pending draft
    try:
        rec, facts = build_default_runner().propose(
            day,
            request_md(ask, route, record.note, new_ids),
            p / "charts",
            merge=keep_untouched(record.note, route, new_ids),
        )
        exhibits = carry_layout(record, rec.note, rec.exhibits)
        exhibits, _ = renumber(rec.note, exhibits, rec.findings, facts, p / "charts")
        rec = rec.model_copy(update={"exhibits": exhibits})
        summary = summarize(record.note, rec.note)
        atomic_write_text(p / "record.json", rec.model_dump_json(indent=2))
        atomic_write_text(p / "facts.json", json.dumps([f.model_dump() for f in facts], indent=1))
        meta = {
            "day": day,
            "ask": ask,
            "kind": route.kind,
            "agent": out["agent"],
            "added": out["added"],
            "summary": summary,
            "base": base,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        atomic_write_text(p / "meta.json", json.dumps(meta, indent=1))  # written last: the marker
    except Exception:
        shutil.rmtree(p, ignore_errors=True)
        raise
    progress("Checked every figure against its sources and drew the charts")
    return out | {"summary": summary, "message": summary["text"]}


@_locked
def approve(day: str) -> str:
    """Make the pending draft the day's note (old one backed up) and drop the proposal."""
    from castelino.agents.update.runner import backup_day

    _, updates_dir = desk._dirs()
    p = _pdir(day)
    if not (p / "meta.json").exists():
        raise FileNotFoundError(f"no draft waiting for {day}")
    meta = json.loads((p / "meta.json").read_text())
    if meta["base"] != _hash(updates_dir, day):
        raise StaleProposalError(
            "the note changed after this draft was made (a re-run, rebuild or hand edit), so "
            "approving it would undo that; ask again"
        )
    current = DailyRecordV2.model_validate_json((updates_dir / f"{day}.json").read_text())
    rec = DailyRecordV2.model_validate_json((p / "record.json").read_text())
    backup_day(updates_dir, day)
    charts = updates_dir / "charts" / day
    shutil.rmtree(charts, ignore_errors=True)
    if (p / "charts").exists():
        shutil.copytree(p / "charts", charts)
    atomic_write_text(updates_dir / "raw" / f"{day}.json", (p / "facts.json").read_text())
    rec = rec.model_copy(
        update={
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "hand_edited_at": current.hand_edited_at,  # the Editor kept the hand-edited text
        }
    )
    atomic_write_text(updates_dir / f"{day}.json", rec.model_dump_json(indent=2))
    shutil.rmtree(p)
    return meta["summary"]["text"]


def reject(day: str) -> None:
    shutil.rmtree(_pdir(day), ignore_errors=True)


# ── by hand ────────────────────────────────────────────────────────────────


class HandItem(BaseModel):
    rank: int
    title: str
    body: str
    view: str | None = None


class ChartPlace(BaseModel):
    file: str
    at: int
    after: int | None = None


class HandEdit(BaseModel):
    headline: str
    takeaways: list[str]
    items: list[HandItem]
    charts: list[ChartPlace] = []


MAX_TEXT = 8000


def apply_hand_edit(record: DailyRecordV2, e: HandEdit) -> DailyRecordV2:
    """The record with the desk's text and chart places; raises ValueError on a bad edit."""
    note = record.note
    by = {h.rank: h for h in e.items}
    if set(by) != {it.rank for it in note.items} or len(e.takeaways) != len(note.takeaways):
        raise ValueError("the note changed while you were editing; reload it and edit again")
    texts = [e.headline, *e.takeaways, *(t for h in e.items for t in (h.title, h.body))]
    if any(not t.strip() for t in texts) or any(len(t) > MAX_TEXT for t in texts):
        raise ValueError("every headline, takeaway, title and paragraph needs some text")
    items = []
    for it in note.items:
        h = by[it.rank]
        upd: dict = {"title": h.title.strip(), "body": h.body.strip()}
        if it.view is not None and h.view is not None and h.view.strip():
            upd["view"] = it.view.model_copy(update={"text": h.view.strip()})
        items.append(it.model_copy(update=upd))
    note = note.model_copy(
        update={
            "headline": e.headline.strip(),
            "takeaways": [t.strip() for t in e.takeaways],
            "items": items,
        }
    )
    ranks = {it.rank for it in note.items}
    place = {c.file: c for c in e.charts}
    exhibits = []
    for x in record.exhibits:
        if (c := place.get(x.file)) is not None:
            if c.at not in ranks or (c.after is not None and c.after < 0):
                raise ValueError(f"{x.title} can't go there")
            x = x.model_copy(update={"at": None if c.at == x.item else c.at, "after": c.after})
        exhibits.append(x)
    return record.model_copy(update={"note": note, "exhibits": exhibits})


def check_hand_edit(day: str, e: HandEdit) -> list[str]:
    """Figures the edit adds that its facts don't give (the guard's number check, as warnings)."""
    _, updates_dir = desk._dirs()
    record, facts = desk.load_day(updates_dir, day)
    new = apply_hand_edit(record, e)
    before = set(check_note(record.note, record.findings, facts, items=len(record.note.items)))
    after = check_note(new.note, new.findings, facts, items=len(new.note.items))
    return [w for w in after if w not in before]


@_locked
def save_hand_edit(day: str, e: HandEdit) -> str:
    """Write the edit (old record and charts backed up); redraw the charts when a move changed
    their order."""
    from castelino.agents.update.runner import backup_day

    _, updates_dir = desk._dirs()
    record, facts = desk.load_day(updates_dir, day)
    new = apply_hand_edit(record, e)
    backup_day(updates_dir, day)
    exhibits, redrawn = renumber(
        new.note, new.exhibits, new.findings, facts, updates_dir / "charts" / day
    )
    new = new.model_copy(
        update={
            "exhibits": exhibits,
            "hand_edited_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    atomic_write_text(updates_dir / f"{day}.json", new.model_dump_json(indent=2))
    return "Saved your edits" + (", and renumbered the charts in reading order" if redrawn else "")
