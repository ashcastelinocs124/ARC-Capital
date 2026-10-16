"""Admin Trade Lab API, under /admin/desk/trade so the site's /api/admin/live/* forward reaches it on Fly
(behind ADMIN_PASSWORD there; locally part of `ckm serve`)."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from castelino.agents.trade import runner, store
from castelino.agents.trade.models import Frame

router = APIRouter(prefix="/admin/desk/trade")
_PNG = re.compile(r"^[a-z]+-\d+-\d+\.png$")


class NewIdea(BaseModel):
    idea: str = Field(min_length=10, max_length=600)


class Say(BaseModel):
    talk: Literal[1, 2]
    to: str = "ARC"
    message: str = Field(min_length=1, max_length=2000)


class Picks(BaseModel):
    picks: dict[str, str]


def _do(fn, *args):
    try:
        return fn(*args)
    except KeyError as e:
        raise HTTPException(404, f"not found: {e}") from e
    except runner.Busy as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _idea(idea_id: str) -> dict:
    return _do(store.load, idea_id).model_dump()


@router.get("")
def list_ideas():
    return {
        "ideas": [
            {
                "id": i.id,
                "title": i.frame.title if i.frame else i.idea[:60],
                "idea": i.idea,
                "status": i.status,
                "round": i.round,
                "cost_usd": i.cost_usd,
                "job": i.job.model_dump() if i.job else None,
                "updated_at": i.updated_at,
            }
            for i in store.all()
        ]
    }


@router.post("")
def create(body: NewIdea):
    idea = store.create(body.idea)
    _do(runner.submit, idea.id, "frame_debate")
    return _idea(idea.id)


@router.get("/{idea_id}")
def get(idea_id: str):
    return _idea(idea_id)


@router.patch("/{idea_id}/frame")
def frame(idea_id: str, body: Frame):
    _do(runner.set_frame, idea_id, body)
    return _idea(idea_id)


@router.post("/{idea_id}/rerun-debate")
def rerun(idea_id: str):
    _do(runner.rerun_debate, idea_id)
    return _idea(idea_id)


@router.post("/{idea_id}/talk")
def say(idea_id: str, body: Say):
    msgs = _do(runner.say, idea_id, body.talk, body.to, body.message)
    return {"messages": [m.model_dump() for m in msgs], "idea": _idea(idea_id)}


@router.delete("/{idea_id}/research/{item_id}")
def remove(idea_id: str, item_id: str):
    _do(runner.remove_item, idea_id, item_id)
    return _idea(idea_id)


@router.post("/{idea_id}/research")
def research(idea_id: str):
    _do(runner.send_research, idea_id)
    return _idea(idea_id)


@router.post("/{idea_id}/charts/{section}/another")
def another(idea_id: str, section: str):
    return _do(runner.another, idea_id, section).model_dump()


@router.post("/{idea_id}/charts")
def choose(idea_id: str, body: Picks):
    _do(runner.choose, idea_id, body.picks)
    return _idea(idea_id)


@router.post("/{idea_id}/retry")
def retry(idea_id: str):
    _do(runner.retry, idea_id)
    return _idea(idea_id)


@router.get("/{idea_id}/charts/{name}")
def chart(idea_id: str, name: str):
    p = store.charts_dir(idea_id) / name
    if not _PNG.match(name) or "/" in idea_id or ".." in idea_id or not p.exists():
        raise HTTPException(404, "no such chart")
    return FileResponse(p, media_type="image/png")


@router.delete("/{idea_id}")
def hide(idea_id: str):
    _do(store.hide, idea_id)
    return {"hidden": idea_id}
