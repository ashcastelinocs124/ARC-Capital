"""Admin Daily desk API: per-day agent findings, chat, re-run, rebuild, Substack draft.

Locally it is part of `ckm serve`. On Fly it is the only thing served (dashboard/desk_app.py),
behind the admin password, and the static site reaches it through /api/admin/live/*.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from castelino.agents.update import desk

router = APIRouter(prefix="/admin/desk")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# one background job at a time per day: {"kind", "state": running|done|failed, "message", "at"}
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _day_ok(day: str) -> str:
    if not _DAY.match(day):
        raise HTTPException(400, "day must be YYYY-MM-DD")
    _, updates = desk._dirs()
    if not (updates / f"{day}.json").exists():
        raise HTTPException(404, f"no Morning Note for {day}")
    return day


def _draft(day: str) -> dict | None:
    _, updates = desk._dirs()
    marker = updates / "substack" / f"{day}.json"
    if not marker.exists():
        return None
    draft_id = json.loads(marker.read_text()).get("draft_id")
    pub = os.getenv("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
    return {"id": draft_id, "url": f"{pub}/publish/post/{draft_id}" if pub else None}


@router.get("/days")
def days():
    _, updates = desk._dirs()
    out = []
    for p in sorted(updates.glob("[0-9][0-9][0-9][0-9]-*.json"), reverse=True)[:30]:
        try:
            rec = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if rec.get("version") == 2:
            out.append(
                {
                    "date": rec["date"],
                    "headline": rec["note"]["headline"],
                    "draft": _draft(rec["date"]),
                }
            )
    return {"days": out}


@router.get("/{day}")
def day_detail(day: str):
    _, updates = desk._dirs()
    record, _facts = desk.load_day(updates, _day_ok(day))
    return {
        "date": record.date,
        "generated_at": record.generated_at,
        "note": record.note.model_dump(),
        "findings": [
            f.model_dump(include={"id", "agent", "claim", "fact_ids", "source_title", "source_url"})
            for f in record.findings
        ],
        "draft": _draft(day),
        "job": _jobs.get(day),
    }


class ChatIn(BaseModel):
    messages: list[dict]


@router.post("/{day}/{agent}/chat")
def chat(day: str, agent: str, body: ChatIn):
    if agent not in desk.DESK:
        raise HTTPException(404, f"unknown agent {agent}")
    try:
        return {"answer": desk.chat(_day_ok(day), agent, body.messages)}
    except Exception as e:  # noqa: BLE001 — show the model error in the chat, don't 500
        raise HTTPException(502, f"chat failed: {str(e)[:200]}") from e


def _start(day: str, kind: str, fn) -> dict:
    with _jobs_lock:
        if (_jobs.get(day) or {}).get("state") == "running":
            raise HTTPException(409, f"{_jobs[day]['kind']} is already running for {day}")
        job = _jobs[day] = {
            "kind": kind,
            "state": "running",
            "message": "",
            "at": datetime.now().isoformat(timespec="seconds"),
        }

    def work():
        try:
            job.update(state="done", message=fn())
        except Exception as e:  # noqa: BLE001 — reported to the page
            job.update(state="failed", message=str(e)[:400])

    threading.Thread(target=work, daemon=True).start()
    return job


class RerunIn(BaseModel):
    ask: str


@router.post("/{day}/{agent}/rerun")
def rerun(day: str, agent: str, body: RerunIn):
    if agent not in desk.AGENTS:
        raise HTTPException(404, f"can't re-run {agent}")
    ask = body.ask.strip()[: desk.MAX_CHARS]
    if not ask:
        raise HTTPException(400, "write what the agent should look into")
    return _start(_day_ok(day), f"re-run {agent}", lambda: desk.rerun(day, agent, ask))


@router.post("/{day}/rebuild")
def rebuild(day: str):
    return _start(_day_ok(day), "rebuild", lambda: desk.rebuild(day))


@router.post("/{day}/substack")
def substack(day: str):
    from castelino.substack import push_draft

    return _start(_day_ok(day), "substack", lambda: push_draft(day))
