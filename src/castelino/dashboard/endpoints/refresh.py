"""Dashboard Refresh button: runs the data refreshes on demand (they no longer run at server start).

POST /refresh starts every job in its own daemon thread; GET /refresh/status reports each one.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)
router = APIRouter()


class Skipped(Exception):  # noqa: N818 - an outcome, not an error
    """A job had nothing to do (already fresh, disabled)."""


def job_update_agent() -> str:
    from datetime import date

    from castelino import config
    from castelino.agents.consultants import runner as consultants
    from castelino.agents.update import runner as update_runner

    cfg = config.get_settings()
    if not cfg.update_agent.enabled:
        raise Skipped("disabled in config.yaml (update_agent.enabled)")
    day = date.today()
    consultants.before_note(day)  # topic consultants build first, so the note can use their theses
    result = update_runner.build_default_runner().run_if_due()
    consultants.after_note(day, cfg.root / cfg.update_agent.updates_dir)  # then they review it
    if result == "skipped":
        raise Skipped("today's briefing already exists")
    if result == "locked":
        raise Skipped("another briefing run is in progress")
    if result == "failed":
        raise RuntimeError("briefing run failed; see the Daily Update page")
    return "briefing written"


def job_model_refit() -> str:
    from castelino import config
    from castelino.agents.update import refit
    from castelino.agents.update.registry import ModelRegistry
    from castelino.forecast.regime import rebuild_ism_proxy, train_and_forecast

    try:
        rebuild_ism_proxy()  # Pulse's target is a CSV; without this it never gets a new month
    except Exception:  # noqa: BLE001 — FRED down: refit on the CSV we have
        log.warning("could not rebuild the ISM proxy CSV; using the existing one", exc_info=True)
    cfg = config.get_settings()
    out = refit.run_refit(
        registry=ModelRegistry(cfg.root / cfg.update_agent.data_dir / "models"),
        tolerance=cfg.model_refit.gate_tolerance,
        refit_fn=train_and_forecast,
        latest_month_fn=refit.latest_months,
    )
    if out is None:
        raise Skipped("no new data since the last refit")
    return out


def job_sector_sentiment() -> str:
    from castelino import config
    from castelino.signals import sector_sentiment as ss

    if not config.get_settings().sector_sentiment.enabled:
        raise Skipped("disabled in config.yaml (sector_sentiment.enabled)")
    prev = ss.load_snapshot()
    snap = ss.refresh(force=True)
    if snap.narrative is None and os.environ.get("OPENAI_API_KEY", "").strip():
        from castelino.agents.sector_explainer import explain_snapshot

        prev_text = prev.narrative if prev and prev.as_of != snap.as_of else None
        ss.save_snapshot(explain_snapshot(snap, prev_text))
    return f"{len(snap.sectors)} sectors, {len(snap.stocks)} stocks scored"


def job_adoption() -> str:
    from castelino.adoption.live import run_live

    s = run_live()
    return f"scored {s.n_scored}/{s.n_companies}, {s.n_errors} source errors"


def job_cross_asset() -> str:
    from castelino.cross_asset import run as cross_asset

    try:
        return cross_asset.run()
    except cross_asset.NothingToDo as exc:
        raise Skipped(str(exc)) from exc


def job_week_ahead() -> str:
    from castelino.week_ahead import run as week_ahead

    return week_ahead.run()


def job_ai_sentiment() -> str:
    from castelino.ai_sentiment import run as ai_sentiment

    try:
        return ai_sentiment.run()
    except ai_sentiment.NotConfigured as exc:
        raise Skipped(str(exc)) from exc


def job_weekly_deep_dive() -> str:
    from castelino import config
    from castelino.agents.weekly import runner as weekly_runner

    if not config.get_settings().deep_dive.enabled:
        raise Skipped("disabled in config.yaml (deep_dive.enabled)")
    result = weekly_runner.build_default_runner().run_if_due()
    if result == "skipped":
        raise Skipped("no deep dive due (runs from Sunday for Mon–Fri)")
    if result == "locked":
        raise Skipped("another deep dive run is in progress")
    if result == "failed":
        raise RuntimeError("deep dive failed; see GET /weekly/status")
    return "weekly deep dive written"


LABELS = {
    "update_agent": "Update Agent briefing",
    "model_refit": "Model refit",
    "sector_sentiment": "Sector Sentiment",
    "adoption": "AI Adoption Index",
    "cross_asset": "Cross-Asset Drivers",
    "week_ahead": "Week Ahead",
    "ai_sentiment": "AI Model Sentiment",
    "weekly_deep_dive": "Weekly Deep Dive",
}
# Overridable in tests.
_RUNNERS: dict[str, Callable[[], str]] = {
    "update_agent": job_update_agent,
    "model_refit": job_model_refit,
    "sector_sentiment": job_sector_sentiment,
    "adoption": job_adoption,
    "cross_asset": job_cross_asset,
    "week_ahead": job_week_ahead,
    "ai_sentiment": job_ai_sentiment,
    "weekly_deep_dive": job_weekly_deep_dive,
}
_state: dict[str, dict] = {}
_threads: list[threading.Thread] = []
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _run(key: str, fn: Callable[[], str]) -> None:
    try:
        _state[key].update(status="done", message=fn())
    except Skipped as e:
        _state[key].update(status="skipped", message=str(e))
    except Exception as e:  # noqa: BLE001 - one failed job never stops the others
        log.warning("refresh job %s failed: %s", key, e)
        _state[key].update(status="failed", message=str(e)[:300])
    finally:
        _state[key]["finished_at"] = _now()


def _status() -> dict:
    jobs = [
        {
            "key": k,
            "label": LABELS.get(k, k),
            "status": "idle",
            "message": None,
            "started_at": None,
            "finished_at": None,
            **_state.get(k, {}),
        }
        for k in _RUNNERS
    ]
    return {"running": any(j["status"] == "running" for j in jobs), "jobs": jobs}


def _wait(timeout: float) -> None:
    """Test helper: block until the current refresh threads finish."""
    for t in list(_threads):
        t.join(timeout)


@router.post("/refresh")
def start_refresh():
    with _lock:
        if _status()["running"]:
            return JSONResponse(_status(), status_code=409)
        _threads.clear()
        for key, fn in _RUNNERS.items():
            _state[key] = {
                "status": "running",
                "message": None,
                "started_at": _now(),
                "finished_at": None,
            }
            t = threading.Thread(target=_run, args=(key, fn), name=f"refresh-{key}", daemon=True)
            _threads.append(t)
            t.start()
        return JSONResponse(_status(), status_code=202)


@router.get("/refresh/status")
def refresh_status():
    return _status()
