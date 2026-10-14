"""Theme Charts runs (data/themes/<YYYY-MM-DD>-<am|pm>.json) for the /themes page."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from castelino.agents.themes import _dir, recent_runs

router = APIRouter()
_RUN = re.compile(r"^\d{4}-\d{2}-\d{2}-(am|pm)$")
_EXHIBIT = re.compile(r"^exhibit_\d{1,2}\.png$")
# ponytail: a week of runs on the page and in the static export; page through older ones if wanted
HISTORY = 14


@router.get("/themes/history")
def themes_history():
    keys = ("run_id", "date", "slot", "theme")
    return {"items": [{k: r.get(k, "") for k in keys} for r in recent_runs(_dir(), HISTORY)]}


@router.get("/themes/latest")
def themes_latest():
    runs = recent_runs(_dir(), 1)
    if not runs:
        raise HTTPException(404, "no theme charts yet")
    return runs[0]


@router.get("/themes/{run_id}")
def themes_run(run_id: str):
    p = _dir() / f"{run_id}.json"
    if not _RUN.match(run_id) or not p.is_file():
        raise HTTPException(404, "no such run")
    return json.loads(p.read_text())


@router.get("/themes/{run_id}/charts/{name}")
def themes_chart(run_id: str, name: str):
    p = _dir() / "charts" / run_id / name
    if not _RUN.match(run_id) or not _EXHIBIT.match(name) or not p.is_file():
        raise HTTPException(404, "no such chart")
    return FileResponse(p, media_type="image/png")
