"""Sector sentiment endpoint — serves the stored snapshot; never computes
inline unless ?compute=true is passed explicitly."""

from __future__ import annotations

from fastapi import APIRouter

from castelino.signals import sector_sentiment as ss

router = APIRouter()


@router.get("/sector_sentiment")
def sector_sentiment(compute: bool = False):
    if compute:
        try:
            snap = ss.refresh(force=True)
            return snap.model_dump(mode="json")
        except Exception:
            pass  # fall through to stored snapshot
    snap = ss.load_snapshot()
    return snap.model_dump(mode="json") if snap else {}
