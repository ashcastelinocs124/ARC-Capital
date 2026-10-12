"""GET /week_ahead: serves the stored Week Ahead file; never computes inline."""

from __future__ import annotations

import json

from fastapi import APIRouter

from castelino.week_ahead import run as week_ahead_run

router = APIRouter()


@router.get("/week_ahead")
def week_ahead():
    p = week_ahead_run.out_path()
    return json.loads(p.read_text()) if p.exists() else {}
