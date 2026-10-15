"""Trade Lab → a Substack draft in Special Topics (never published; the user publishes). The draft id lives
in data/trades/<id>/substack.json, so later rounds update the same draft; a deleted draft is recreated and a
published one stops the step. Before a round 2+ rewrite, current_text() reads the draft back so the editor
keeps the user's hand edits."""

from __future__ import annotations

import json
import os
from datetime import date

import httpx

from castelino import substack as sb
from castelino.agents.trade import store
from castelino.agents.trade.editor import SECTION_NAMES
from castelino.agents.trade.models import StepError, TradeIdea

SECTION = 466775  # Substack section "special-topics"


def _sources(idea: TradeIdea) -> list[tuple[str, str]]:
    by = idea.fact_map()
    seen: set[str] = set()
    out = []
    for i in [i for s in idea.report.sections for i in s.fact_ids]:
        f = by.get(i)
        if f and f.source_url and f.source_url not in seen:
            seen.add(f.source_url)
            out.append((f.source_title, f.source_url))
    return out


def doc(idea: TradeIdea, uploaded: dict[str, dict]) -> dict:
    rep = idea.report
    chosen = {o.spec.section: o for o in idea.current().options if o.chosen and o.file}

    def image(section: str) -> list[dict]:
        o = chosen.get(section)
        return [sb._image(uploaded[o.file], o.spec.title)] if o and o.file in uploaded else []

    def bullets(items: list[dict]) -> dict:
        return {
            "type": "bullet_list",
            "content": [{"type": "list_item", "content": [i]} for i in items],
        }

    c: list[dict] = [sb._p(*sb._rich(p)) for p in rep.introduction]
    c.append(sb._heading("Key takeaways"))
    c.append(bullets([sb._p(*sb._rich(t)) for t in rep.takeaways]))
    c += image("intro")
    for n, s in enumerate(rep.sections, 1):
        c.append(
            sb._heading(f"{n}. {SECTION_NAMES[s.key]}")
        )  # fixed names; the editor's heading is ignored
        c += [sb._p(*sb._rich(p)) for p in s.paragraphs]
        c += image(s.key)
    c.append(sb._p(*sb._rich(f"**What to watch:** {rep.what_to_watch}")))
    c += image("watch")
    if src := _sources(idea):
        c.append(sb._heading("Sources"))
        c.append(bullets([sb._p(sb._text(t, u)) for t, u in src]))
    footer = "Charts are drawn by ARC from Yahoo Finance and FRED data. Not investment advice."
    c.append(sb._p(sb._text(footer)))
    return {"type": "doc", "content": c}


def _set_section(draft_id: int) -> None:
    pub = os.environ["SUBSTACK_PUBLICATION_URL"].rstrip("/")
    fields = {"draft_section_id": SECTION, "section_chosen": True}
    with httpx.Client(cookies={"substack.sid": os.environ["SUBSTACK_SID"]}, timeout=60) as http:
        sb._check(http.put(f"{pub}/api/v1/drafts/{draft_id}", json=fields))


def push(idea: TradeIdea) -> dict:
    chosen = [o for o in idea.current().options if o.chosen and o.file]
    marker = store.idea_dir(idea.id) / "substack.json"
    msg = sb.push(
        marker=marker,
        title=idea.report.title,
        subtitle=f"ARC Special Topics · {idea.frame.title} · {date.today():%B %-d, %Y}",
        pngs={o.file: store.charts_dir(idea.id) / o.file for o in chosen},
        body=lambda up: doc(idea, up),
        label=f"Trade Lab {idea.id}",
    )
    if msg.startswith("skipped"):
        raise StepError(f"Substack: {msg}")
    draft_id = json.loads(marker.read_text())["draft_id"]
    _set_section(draft_id)
    pub = os.environ.get("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
    return {"draft_id": draft_id, "url": f"{pub}/publish/post/{draft_id}"}


def _get(draft_id: int) -> dict:
    pub = os.environ["SUBSTACK_PUBLICATION_URL"].rstrip("/")
    with httpx.Client(cookies={"substack.sid": os.environ["SUBSTACK_SID"]}, timeout=60) as http:
        return sb._check(http.get(f"{pub}/api/v1/drafts/{draft_id}")).json()


def current_text(idea: TradeIdea, *, get=None) -> str | None:
    if not idea.substack:
        return None
    body = json.loads((get or _get)(idea.substack["draft_id"]).get("draft_body") or "{}")

    def text(n: dict) -> str:
        return n.get("text", "") + "".join(text(k) for k in n.get("content", []))

    blocks = [text(n).strip() for n in body.get("content", [])]
    return "\n\n".join(b for b in blocks if b) or None
