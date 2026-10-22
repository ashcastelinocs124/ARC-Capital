"""Admin Topic Consultants API, under /admin/desk/consultants so the site's /api/admin/live/* forward
reaches it on Fly (behind ADMIN_PASSWORD there; locally part of `ckm serve`)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from castelino.agents.consultants import planner, runner, store
from castelino.agents.consultants.models import Consultant, Watchlist
from castelino.agents.trade import llm

router = APIRouter(prefix="/admin/desk/consultants")


class Topic(BaseModel):
    topic: str = Field(min_length=3, max_length=200)


class NewConsultant(Topic):
    watchlist: Watchlist


def _load(slug: str) -> Consultant:
    try:
        return store.load(slug)
    except KeyError as e:
        raise HTTPException(404, f"no consultant {slug!r}") from e


def _row(c: Consultant) -> dict:
    today = date.today().isoformat()
    hist = store.history(c.slug)
    return {
        **c.model_dump(include={"slug", "code", "topic", "status", "error", "created"}),
        "last": hist[-1].model_dump() if hist else None,
        "facts_today": len(store.read_facts(c.slug, today)),
        "asks_today": len(store.day_log(c.slug, today).asks),
    }


def _notes(notes) -> list[dict]:
    return [{**asdict(n), "last_used": n.last_used.isoformat()} for n in notes]


@router.get("")
def list_consultants():
    return {"consultants": [_row(c) for c in store.all()]}


@router.post("/plan")
def plan(req: Topic):
    return {"watchlist": planner.suggest(req.topic.strip(), llm.Meter())}


@router.post("")
def create(req: NewConsultant):
    c = store.create(req.topic, req.watchlist)
    runner.submit_start(c.slug)
    return _row(c)


@router.get("/{slug}")
def get(slug: str):
    c = _load(slug)
    days = store.fact_days(slug)
    day = days[-1] if days else date.today().isoformat()
    short, long = store.read_memory(slug)
    t = store.read_thesis(slug)
    return {
        "consultant": c.model_dump(),
        "thesis": t.model_dump() if t else None,
        "history": [h.model_dump() for h in reversed(store.history(slug))],  # newest first
        "today": {
            "day": day,
            "facts": [f.model_dump() for f in store.read_facts(slug, day)],
            "asks": [a.model_dump() for a in store.day_log(slug, day).asks],
            "notes": store.day_log(slug, day).notes,
        },
        "memory": {"short": _notes(short), "long": _notes(long)},
        # today's own log: a cost-cap skip or a failure shows even on a day with no facts
        "log": store.day_log(slug, date.today().isoformat()).model_dump(),
    }


def _set_status(slug: str, status: str) -> dict:
    _load(slug)
    with store.edit(slug) as x:
        x.status = status
    return _row(store.load(slug))


@router.post("/{slug}/pause")
def pause(slug: str):
    return _set_status(slug, "paused")


@router.post("/{slug}/resume")
def resume(slug: str):
    return _set_status(slug, "active")


@router.post("/{slug}/build")
def build_now(slug: str):
    """Build now: the retry for a consultant whose build failed. Shows as building (the tab polls)."""
    _load(slug)
    with store.edit(slug) as x:
        x.status, x.error = "building", None
    runner.submit_start(slug)
    return _row(store.load(slug))


@router.delete("/{slug}")
def delete(slug: str):
    _load(slug)
    store.hide(slug)
    return {"deleted": slug}
