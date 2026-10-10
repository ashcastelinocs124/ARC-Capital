"""GET /cross_asset: serves the stored Cross-Asset Drivers snapshot; never computes inline."""

from __future__ import annotations

import json

from fastapi import APIRouter

from castelino.cross_asset import run as cross_asset_run

router = APIRouter()


@router.get("/cross_asset")
def cross_asset():
    p = cross_asset_run.out_path()
    return json.loads(p.read_text()) if p.exists() else {}
