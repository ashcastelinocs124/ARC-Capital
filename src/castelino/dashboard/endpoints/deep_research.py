"""Admin General Deep Research API, under /admin/desk/research so the site's /api/admin/live/* forward
reaches it on Fly (behind ADMIN_PASSWORD there; locally part of `ckm serve`)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from castelino.agents.research.deep import clarifier, editor_desk, runner, store
from castelino.agents.research.deep.models import Busy, ResearchSession
from castelino.agents.trade import llm
from castelino.config import get_settings

router = APIRouter(prefix="/admin/desk/research")


class NewTopic(BaseModel):
    topic: str = Field(min_length=3, max_length=500)


class Answers(BaseModel):
    answers: dict[str, str] = {}


class Ask(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def _public(s: ResearchSession) -> dict:
    d = s.model_dump(mode="json")
    for a in d["agents"]:
        a.pop("transcript", None)  # prompts and raw tool output stay on the server
    d["cost_cap_usd"] = get_settings().deep_research.cost_cap_usd
    return d


def _do(fn, *args):
    try:
        return fn(*args)
    except KeyError as e:
        raise HTTPException(404, f"not found: {e}") from e
    except Busy as e:
        raise HTTPException(409, str(e)) from e


@router.get("")
def list_sessions():
    rows = []
    for s in store.all():
        runner.maybe_compact(s)
        rows.append(
            {
                "id": s.id,
                "topic": s.topic,
                "status": s.status,
                "job": s.job.model_dump() if s.job else None,
                "pending": sum(p.status == "pending" for p in s.proposals),
                "cost_usd": s.cost_usd,
                "created_at": s.created_at,
                "compacted": bool(s.compacted_at),
            }
        )
    return {"sessions": rows}


@router.post("")
def create(req: NewTopic):
    meter = llm.Meter()
    clar = clarifier.clarify(req.topic, meter)
    return _public(store.create(req.topic, clar, meter.total))


@router.get("/{sid}")
def get(sid: str):
    runner.maybe_compact(_do(store.load, sid))
    return _public(_do(store.load, sid))


def _start(sid: str, answers: dict[str, str]) -> None:
    with store.edit(sid) as s:
        if s.status != "awaiting_answers":
            raise Busy("research already started")
        s.answers = {k: v.strip() for k, v in answers.items() if v.strip()}
        s.status = "researching"
    runner.submit(sid, "run")


@router.post("/{sid}/answers")
def answers(sid: str, req: Answers):
    _do(_start, sid, req.answers)
    return _public(store.load(sid))


def _retry(sid: str) -> None:
    s = store.load(sid)
    if not s.job or s.job.state not in ("failed", "interrupted"):
        raise Busy("nothing to retry")
    runner.submit(sid, s.job.step)


@router.post("/{sid}/retry")
def retry(sid: str):
    _do(_retry, sid)
    return _public(store.load(sid))


def _ask(sid: str, pid: str, text: str) -> None:
    runner.submit_ask(sid, editor_desk.start(sid, pid, text).n)


@router.post("/{sid}/points/{pid}/ask")
def ask(sid: str, pid: str, req: Ask):
    _do(_ask, sid, pid, req.text)
    return _public(store.load(sid))


@router.post("/{sid}/proposals/{n}/approve")
def approve(sid: str, n: int):
    _do(editor_desk.approve, sid, n)
    return _public(store.load(sid))


@router.post("/{sid}/proposals/{n}/reject")
def reject(sid: str, n: int):
    _do(editor_desk.reject, sid, n)
    return _public(store.load(sid))
