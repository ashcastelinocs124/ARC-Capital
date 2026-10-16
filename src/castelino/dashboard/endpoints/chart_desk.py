"""Admin Charts API (chart desk), under /admin/desk/charts so the site's /api/admin/live/* forward
reaches it on Fly (behind ADMIN_PASSWORD there; locally part of `ckm serve`). Mounted before the
Daily desk, whose /admin/desk/{day} would otherwise catch /admin/desk/charts."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from castelino.agents import chart_desk as desk
from castelino.config import get_settings

router = APIRouter(prefix="/admin/desk/charts")
_PNG = re.compile(r"^[tm]\d+-\d+\.png$")


class ChatIn(BaseModel):
    ask: str = Field(min_length=3, max_length=1500)
    model: str | None = None
    run_id: str | None = None


class CompareIn(BaseModel):
    ask: str = Field(min_length=3, max_length=1500)
    models: list[str]


class VoteIn(BaseModel):
    model: str


def _do(fn, *args):
    try:
        return fn(*args).model_dump()
    except KeyError as e:
        raise HTTPException(404, f"not found: {e}") from e
    except desk.Busy as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("")
def overview():
    cfg = get_settings().chart_desk
    return {
        "chat_model": cfg.chat_model,
        "compare_models": cfg.compare_models,
        "compare_default": cfg.compare_models[: cfg.compare_default],
        "scoreboard": desk.scoreboard(),
        "runs": [
            {
                "id": r.id,
                "kind": r.kind,
                "title": r.title,
                "updated_at": r.updated_at,
                "turns": len(r.turns),
                "models": sorted({rep.model for t in r.turns for rep in t.replies}),
                "vote": r.vote,
            }
            for r in desk.all_runs()[:40]
        ],
    }


@router.post("/chat")
def chat(body: ChatIn):
    return _do(desk.chat, body.ask, body.model, body.run_id)


@router.post("/compare")
def compare(body: CompareIn):
    return _do(desk.compare, body.ask, body.models)


@router.get("/{run_id}")
def get_run(run_id: str):
    return _do(desk.load, run_id)


@router.post("/{run_id}/vote")
def vote(run_id: str, body: VoteIn):
    return _do(desk.vote, run_id, body.model)


@router.get("/{run_id}/png/{name}")
def png(run_id: str, name: str):
    _do(desk.load, run_id)  # 404 for an unknown run
    p = desk.run_dir(run_id) / name
    if not _PNG.match(name) or not p.exists():
        raise HTTPException(404, "no such chart")
    return FileResponse(p, media_type="image/png")
