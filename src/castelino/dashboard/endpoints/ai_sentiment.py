"""GET /ai_sentiment: serves the stored AI Model Sentiment file; never computes inline."""

from __future__ import annotations

import json

from fastapi import APIRouter

from castelino.ai_sentiment import run as ai_sentiment_run

router = APIRouter()


@router.get("/ai_sentiment")
def ai_sentiment():
    p = ai_sentiment_run.out_path()
    return json.loads(p.read_text()) if p.exists() else {}
