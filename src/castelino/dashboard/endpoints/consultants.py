"""Admin Topic Consultants API, under /admin/desk/consultants so the site's /api/admin/live/* forward
reaches it on Fly (behind ADMIN_PASSWORD there; locally part of `ckm serve`)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from castelino.agents.consultants import planner, runner, store
from castelino.agents.consultants.models import Consultant, Watchlist
from castelino.agents.themes import SERIES
from castelino.agents.trade import llm

router = APIRouter(prefix="/admin/desk/consultants")


class Topic(BaseModel):
    topic: str = Field(min_length=3, max_length=200)


class NewConsultant(Topic):
    watchlist: Watchlist


class Knob(BaseModel):
    on: bool


class Check(BaseModel):
    kind: Literal["company", "series"]
    value: str = Field(min_length=1, max_length=40)


def _valid(wl: Watchlist) -> Watchlist:
    """A watchlist from the browser: series in fred:/yahoo: form and the hand-edit caps."""
    if bad := [s for s in wl.series if not SERIES.match(s)]:
        raise HTTPException(422, f"not fred:ID or yahoo:TICKER: {', '.join(bad)}")
    if max(len(wl.companies), len(wl.series)) > planner.MAX_HAND:
        raise HTTPException(
            422, f"at most {planner.MAX_HAND} companies and {planner.MAX_HAND} series"
        )
    return wl


def _load(slug: str) -> Consultant:
    try:
        return store.load(slug)
    except KeyError as e:
        raise HTTPException(404, f"no consultant {slug!r}") from e


def _row(c: Consultant) -> dict:
    today = date.today().isoformat()
    hist = store.history(c.slug)
    return {
        **c.model_dump(
            include={"slug", "code", "topic", "status", "error", "created", "post_to_x"}
        ),
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


@router.post("/check")
def check(req: Check):
    """One hand-added company (by ticker) or series, checked against Yahoo/FRED before it becomes a chip."""
    try:
        if req.kind == "company":
            return {"company": planner.check_company(req.value).model_dump()}
        return {"series": planner.check_series(req.value)}
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("")
def create(req: NewConsultant):
    c = store.create(req.topic, _valid(req.watchlist))
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


@router.post("/{slug}/x")
def set_post_to_x(slug: str, req: Knob):
    """The posting knob: on = the evening review may post one notable point a day to X (post.py)."""
    _load(slug)
    with store.edit(slug) as x:
        x.post_to_x = req.on
    return _row(store.load(slug))


@router.get("/{slug}/posts/{day}.png")
def post_chart(slug: str, day: str):
    """The chart that went out with that day's post."""
    _load(slug)
    try:
        date.fromisoformat(day)
    except ValueError as e:
        raise HTTPException(404, "no such day") from e
    path = store.cdir(slug) / "posts" / f"{day}.png"
    if not path.exists():
        raise HTTPException(404, "no post chart that day")
    return FileResponse(path, media_type="image/png")


@router.put("/{slug}/watchlist")
def set_watchlist(slug: str, wl: Watchlist):
    """Edit a running consultant's watchlist. Today's facts and view stay; the next build fetches it."""
    _load(slug)
    _valid(wl)
    with store.edit(slug) as x:
        x.watchlist = wl
    return {"watchlist": wl.model_dump()}


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
