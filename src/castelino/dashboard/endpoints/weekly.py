"""Weekly Deep Dive records (data/deep/<YYYY-Www>.json) for the Deep Research page."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from castelino.agents.update.runner import read_status
from castelino.agents.weekly.inputs import due_week
from castelino.agents.weekly.runner import _today_et
from castelino.config import get_settings

router = APIRouter()
_WEEK = re.compile(r"^\d{4}-W\d{2}$")
_EXHIBIT = re.compile(r"^exhibit_\d{1,2}\.png$")


def _dir() -> Path:
    cfg = get_settings()
    return cfg.root / cfg.deep_dive.data_dir


def _weeks(d: Path) -> list[str]:
    return sorted((p.stem for p in d.glob("????-W??.json")), reverse=True)


def _load(d: Path, week: str) -> dict:
    return json.loads((d / f"{week}.json").read_text())


@router.get("/weekly/status")
def weekly_status():
    d = _dir()
    st = read_status(d)
    st["due"] = due_week(_today_et(), d)
    return st


@router.get("/weekly/history")
def weekly_history():
    d = _dir()
    items = []
    for w in _weeks(d):
        try:
            rec = _load(d, w)
            title = (rec.get("report") or {}).get("title", "")
            items.append(
                {
                    "week": w,
                    "start": rec.get("start", ""),
                    "end": rec.get("end", ""),
                    "title": title,
                }
            )
        except (OSError, ValueError, AttributeError):  # half-written or malformed file
            items.append({"week": w, "start": "", "end": "", "title": ""})
    return {"items": items}


@router.get("/weekly/latest")
def weekly_latest():
    d = _dir()
    weeks = _weeks(d)
    if not weeks:
        raise HTTPException(404, "no weekly deep dive yet")
    return _load(d, weeks[0])


@router.get("/weekly/{week}/charts/{name}")
def weekly_chart(week: str, name: str):
    p = _dir() / "charts" / week / name
    if not _WEEK.match(week) or not _EXHIBIT.match(name) or not p.is_file():
        raise HTTPException(404, "no such chart")
    return FileResponse(p, media_type="image/png")


@router.get("/weekly/{week}")
def weekly_by_week(week: str):
    d = _dir()
    if not _WEEK.match(week) or not (d / f"{week}.json").is_file():
        raise HTTPException(404, "no such week")
    return _load(d, week)
