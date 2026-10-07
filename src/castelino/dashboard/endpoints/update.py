from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from castelino.agents.update.runner import read_status
from castelino.config import get_settings

router = APIRouter()
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EXHIBIT = re.compile(r"^exhibit_\d{1,2}\.png$")


def _dirs() -> tuple[Path, Path]:
    cfg = get_settings()
    return cfg.root / cfg.update_agent.data_dir, cfg.root / cfg.update_agent.updates_dir


def _days(updates_dir: Path) -> list[str]:
    return sorted((p.stem for p in updates_dir.glob("????-??-??.json")), reverse=True)


def _load(updates_dir: Path, day: str):
    return json.loads((updates_dir / f"{day}.json").read_text())


@router.get("/update/status")
def update_status():
    data_dir, updates_dir = _dirs()
    st = read_status(data_dir)
    st["has_today"] = (updates_dir / f"{date.today().isoformat()}.json").exists()
    return st


@router.get("/update/history")
def update_history():
    """Newest first. `items` carries each day's headline for the Past updates list."""
    updates_dir = _dirs()[1]
    days = _days(updates_dir)
    items = []
    for day in days:
        try:
            rec = _load(updates_dir, day)
            headline = ((rec.get("note") or rec.get("update")) or {}).get("headline") or ""
        except (OSError, ValueError, AttributeError):  # a half-written or malformed file
            headline = ""
        items.append({"date": day, "headline": headline})
    return {"dates": days, "items": items}


@router.get("/update/latest")
def update_latest():
    updates_dir = _dirs()[1]
    days = _days(updates_dir)
    if not days:
        raise HTTPException(404, "no briefing yet")
    return _load(updates_dir, days[0])


@router.get("/update/{day}/charts/{name}")
def update_chart(day: str, name: str):
    p = _dirs()[1] / "charts" / day / name
    if not _DAY.match(day) or not _EXHIBIT.match(name) or not p.is_file():
        raise HTTPException(404, "no such chart")
    return FileResponse(p, media_type="image/png")


@router.get("/update/{day}")
def update_by_day(day: str):
    updates_dir = _dirs()[1]
    if not _DAY.match(day) or not (updates_dir / f"{day}.json").is_file():
        raise HTTPException(404, "no such briefing")
    return _load(updates_dir, day)
