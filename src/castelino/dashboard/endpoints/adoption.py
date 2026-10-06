"""AI Adoption Index: read-only views over the SQLite store."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from castelino import config
from castelino.adoption.index import headline
from castelino.adoption.models import BUCKETS
from castelino.adoption.store import AdoptionStore
from castelino.adoption.universe import load_universe

router = APIRouter()

# Overridable in tests (set to a tmp_path Path to avoid reading data/adoption).
_store_path = None


def _store() -> AdoptionStore:
    return AdoptionStore(_store_path) if _store_path else AdoptionStore()


def _names() -> dict[str, str]:
    """ticker -> company name from universe.csv; empty when the file is missing."""
    cfg = config.get_settings()
    path = cfg.root / cfg.adoption.data_dir / "universe.csv"
    return {c.ticker: c.name for c in load_universe(path)} if path.exists() else {}


@router.get("/adoption/summary")
def adoption_summary():
    st = _store()
    periods = st.periods()
    if not periods:
        return {"period": None, "headline": {}, "series": [], "cells": []}
    period = periods[-1]
    cells = st.cells(period)
    return {
        "period": period,
        "headline": headline(cells),
        "series": st.series(),
        "stats": st.period_stats(period),
        "cells": [
            {
                "sector": c.sector,
                "bucket": c.bucket,
                "n": c.n,
                "ew": c.ew,
                "cw": c.cw,
                "thin": c.thin,
            }
            for c in cells
            if c.sector is not None
        ],
    }


@router.get("/adoption/companies")
def adoption_companies(sector: str | None = None, bucket: str | None = None):
    """Latest-period companies, optionally narrowed to one sector and/or bucket."""
    if bucket is not None and bucket not in BUCKETS:
        raise HTTPException(status_code=400, detail=f"bucket must be one of {BUCKETS}")
    st = _store()
    periods = st.periods()
    if not periods:
        return []
    names = _names()
    return [
        {
            "ticker": r["ticker"],
            "name": names.get(r["ticker"], ""),
            "bucket": r["bucket"],
            "sector": r["sector"],
            "market_cap": r["market_cap"],
            "score": r["score"],
            "s_talk": r["s_talk"],
            "s_hire": r["s_hire"],
            "s_spend": r["s_spend"],
            "claims": st.claims_for(r["ticker"], r["accession"]),
        }
        for r in st.companies(periods[-1], sector=sector, bucket=bucket)
    ]
