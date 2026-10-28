"""GET /dashboards/ai-capex: serves the stored AI Demand & Capex file and its link card; never computes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from castelino.dashboards.ai_capex import run as ai_capex

router = APIRouter()


@router.get("/dashboards/ai-capex")
def ai_capex_dashboard():
    p = ai_capex.out_path()
    return json.loads(p.read_text()) if p.exists() else {}


@router.get("/dashboards/ai-capex/card.png")
def ai_capex_card():
    p = ai_capex.out_path().parent / "ai_capex" / "card.png"
    if not p.exists():
        raise HTTPException(status_code=404, detail="no card yet")
    return FileResponse(p, media_type="image/png")
