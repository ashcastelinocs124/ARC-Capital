"""Tracked-figures dashboard endpoints.

Wave 8 Task 8.1 — surface the figure-deviation engine's runtime state to
the React frontend. List + detail views for every TrackedFigure currently
configured, including baselines, last firings, and recent posts.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from castelino.config import get_settings
from castelino.triggers.figure_deviation.baseline_store import (
    BaselineStore,
    LexiconVersionMismatch,
)
from castelino.triggers.figure_deviation.profile.store import FigureProfileStore

router = APIRouter()


# ────────────────────────── response shapes ────────────────────────────────


class _LexiconStatus(BaseModel):
    name: str
    threshold_sigma: float
    window_size: int
    baseline_present: bool
    baseline_mean: float | None = None
    baseline_std: float | None = None
    baseline_n_samples: int | None = None
    baseline_last_refreshed: datetime | None = None
    baseline_error: str | None = None  # populated on version mismatch


class _FigureSummary(BaseModel):
    id: str
    display_name: str
    source_types: list[str]
    lexicons: list[str]
    profile_built: bool


class _FigureDetail(BaseModel):
    id: str
    display_name: str
    source_types: list[str]
    lexicons: list[_LexiconStatus]
    profile_built: bool
    profile_version: int | None = None


# ────────────────────────── endpoints ──────────────────────────────────────


@router.get("/figures")
def list_tracked_figures() -> list[_FigureSummary]:
    """All currently-configured tracked figures + their lexicons."""
    cfg = get_settings()
    out: list[_FigureSummary] = []
    base_dir = cfg.resolved_paths.data / "figure_baselines"
    profile_root = cfg.resolved_paths.data / "figure_profiles"
    for fig in cfg.figure_deviation.figures:
        store = FigureProfileStore(figure_id=fig.id, base_dir=profile_root)
        out.append(_FigureSummary(
            id=fig.id,
            display_name=fig.display_name,
            source_types=[s.type for s in fig.sources],
            lexicons=[lex.name for lex in fig.lexicons],
            profile_built=store.is_built(),
        ))
    return out


@router.get("/figures/{figure_id}")
def get_tracked_figure(figure_id: str) -> _FigureDetail:
    cfg = get_settings()
    fig = next(
        (f for f in cfg.figure_deviation.figures if f.id == figure_id), None,
    )
    if fig is None:
        raise HTTPException(status_code=404, detail=f"unknown figure: {figure_id}")

    base_dir = cfg.resolved_paths.data / "figure_baselines"
    lex_dir = Path("data/lexicons")
    profile_root = cfg.resolved_paths.data / "figure_profiles"

    baselines_store = BaselineStore(base_dir=base_dir, lexicon_dir=lex_dir)
    lexicon_statuses: list[_LexiconStatus] = []
    for lex in fig.lexicons:
        status = _LexiconStatus(
            name=lex.name,
            threshold_sigma=lex.threshold_sigma,
            window_size=lex.window_size,
            baseline_present=False,
        )
        try:
            base = baselines_store.load(
                figure_id=figure_id, lexicon_name=lex.name,
            )
            status.baseline_present = True
            status.baseline_mean = base.mean
            status.baseline_std = base.std
            status.baseline_n_samples = base.n_samples
            status.baseline_last_refreshed = base.last_refreshed
        except FileNotFoundError as e:
            status.baseline_error = str(e)
        except LexiconVersionMismatch as e:
            status.baseline_error = str(e)
        lexicon_statuses.append(status)

    profile_store = FigureProfileStore(figure_id=figure_id, base_dir=profile_root)
    meta = profile_store.read_meta()

    return _FigureDetail(
        id=fig.id,
        display_name=fig.display_name,
        source_types=[s.type for s in fig.sources],
        lexicons=lexicon_statuses,
        profile_built=profile_store.is_built(),
        profile_version=meta.version if meta else None,
    )
