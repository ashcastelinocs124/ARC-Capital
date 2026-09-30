from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.gate import run_gate
from castelino.agents.update.guard import find_unsupported
from castelino.agents.update.memory import MemoryStore
from castelino.agents.update.models import (
    DailyRecord, DailyUpdate, GateResult, MarketSnapshot, PredictionDelta, Stage,
)
from castelino.agents.update.registry import MODELS, ModelRegistry
from castelino.forecast.regime import RegimeForecast

log = logging.getLogger(__name__)
_STALE_LOCK_SECONDS = 30 * 60


def read_status(data_dir: Path) -> dict:
    p = Path(data_dir) / "status.json"
    try:
        st = json.loads(p.read_text())
        if isinstance(st, dict) and "stage" in st:
            return st
    except (OSError, json.JSONDecodeError):
        pass
    return {"stage": Stage.IDLE.value}


def _prediction(champion: RegimeForecast | None, current: RegimeForecast | None,
                gate: GateResult | None) -> dict[str, PredictionDelta]:
    if current is None:
        return {}
    out: dict[str, PredictionDelta] = {}
    for m in MODELS:
        old = getattr(champion, m).prob_up if champion else None
        out[m] = PredictionDelta(
            old=round(old, 4) if old is not None else None,
            new=round(getattr(current, m).prob_up, 4),
            gate=getattr(gate, m).decision.value if gate else "unchanged")
    return out


class UpdateRunner:
    def __init__(
        self, *, data_dir: Path, updates_dir: Path, registry: ModelRegistry,
        memory: MemoryStore, tolerance: float, max_retries: int,
        refit_fn: Callable[[], RegimeForecast],
        latest_month_fn: Callable[[], dict[str, str]],
        collect_fn: Callable[..., MarketSnapshot],
        agent_fn: Callable[[MarketSnapshot, str, str, list[str] | None], DailyUpdate],
        today_fn: Callable[[], date] = date.today,
    ):
        self.data_dir, self.updates_dir = Path(data_dir), Path(updates_dir)
        self.registry, self.memory = registry, memory
        self.tolerance, self.max_retries = tolerance, max_retries
        self.refit_fn, self.latest_month_fn = refit_fn, latest_month_fn
        self.collect_fn, self.agent_fn, self.today_fn = collect_fn, agent_fn, today_fn
        self._day = ""

    # ── status + lock ──────────────────────────────────────────────────────
    def _set(self, stage: Stage, error: str | None = None) -> None:
        atomic_write_text(self.data_dir / "status.json", json.dumps(
            {"stage": stage.value, "date": self._day, "error": error}))

    @staticmethod
    def _owner_alive(lock: Path) -> bool:
        try:
            pid = int(lock.read_text().strip())
            os.kill(pid, 0)
            return True
        except PermissionError:          # exists, owned by another user
            return True
        except (ValueError, OSError):    # no/garbage pid, or no such process
            return False

    def _acquire(self) -> bool:
        lock = self.data_dir / "run.lock"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return True
            except FileExistsError:
                try:
                    fresh = time.time() - os.path.getmtime(lock) <= _STALE_LOCK_SECONDS
                    if fresh and self._owner_alive(lock):
                        return False
                    lock.unlink()                    # owner died (killed server) or lock is stale
                except FileNotFoundError:
                    continue
        return False

    def _release(self) -> None:
        (self.data_dir / "run.lock").unlink(missing_ok=True)

    # ── public entrypoint ──────────────────────────────────────────────────
    def run_if_due(self) -> str:
        today = self.today_fn()
        self._day = today.isoformat()
        if (self.updates_dir / f"{self._day}.json").exists():
            return "skipped"
        if not self._acquire():
            return "locked"
        try:
            self._run(today)
            self._set(Stage.DONE)
            return "done"
        except Exception as exc:  # noqa: BLE001 — a failed run must leave no partial output
            log.exception("update agent run failed")
            self._set(Stage.FAILED, error=str(exc)[:300])
            return "failed"
        finally:
            self._release()

    # ── pipeline ───────────────────────────────────────────────────────────
    def _new_data(self, champion: RegimeForecast | None) -> bool:
        if champion is None:
            return True
        try:
            latest = self.latest_month_fn()
        except Exception:  # noqa: BLE001 — if we cannot tell, attempt the refit
            log.warning("new-data check failed; attempting refit", exc_info=True)
            return True
        return any(latest[m] > getattr(champion, m).feature_month[:7] for m in MODELS)

    def _run(self, today: date) -> None:
        self._set(Stage.CHECKING)
        champion = self.registry.current()
        gate: GateResult | None = None
        model_note: str | None = None

        if self._new_data(champion):
            self._set(Stage.REFITTING)
            challenger = None
            try:
                challenger = self.refit_fn()
            except Exception as exc:  # noqa: BLE001 — champion stays, briefing still ships
                log.warning("refit failed", exc_info=True)
                model_note = f"model not refreshed today: {exc}"
            if challenger is not None:
                self._set(Stage.GATING)
                gate = run_gate(challenger, champion, self.tolerance)
                promoted = [m for m in MODELS if getattr(gate, m).decision.value == "promoted"]
                if promoted:
                    version = self.registry.save_version(challenger)
                    for m in promoted:
                        self.registry.set_pointer(m, version)

        self._set(Stage.COLLECTING)
        prediction = _prediction(champion, self.registry.current(), gate)
        snapshot = self.collect_fn(today=self._day, prediction=prediction, model_note=model_note)

        self._set(Stage.WRITING)
        mem, long = self.memory.read_short(), self.memory.read_long()
        update = self.agent_fn(snapshot, mem, long, None)
        self._set(Stage.GUARDING)
        errors = find_unsupported(update, snapshot)
        retries = 0
        while errors and retries < self.max_retries:
            retries += 1
            self._set(Stage.WRITING)
            update = self.agent_fn(snapshot, mem, long, errors)
            self._set(Stage.GUARDING)
            errors = find_unsupported(update, snapshot)
        if errors:
            raise RuntimeError(f"guard failed: figures not in snapshot: {errors}")

        self.memory.apply(update, snapshot, today)
        record = DailyRecord(date=self._day, generated_at=datetime.now().isoformat(timespec="seconds"),
                             snapshot=snapshot, update=update, gate=gate)
        # written last: its existence is what marks the day done
        atomic_write_text(self.updates_dir / f"{self._day}.json", record.model_dump_json(indent=2))


# ── production wiring ──────────────────────────────────────────────────────


def default_latest_months() -> dict[str, str]:
    from castelino.forecast import regime as r

    out: dict[str, str] = {}
    for name, yaml in (("growth", r.GROWTH_INDICATORS_YAML),
                       ("inflation", r.INFLATION_INDICATORS_YAML)):
        target = r.IndicatorListConfig.from_yaml(yaml).target
        s = r._to_month_end(r._resolve_spec(target)).dropna()
        out[name] = pd.Timestamp(s.index.max()).strftime("%Y-%m")
    return out


def build_default_runner() -> UpdateRunner:
    from castelino.agents.update.agent import write_update
    from castelino.agents.update.collector import collect
    from castelino.config import get_settings
    from castelino.forecast.regime import train_and_forecast

    cfg = get_settings()
    ua = cfg.update_agent
    data_dir = cfg.root / ua.data_dir
    return UpdateRunner(
        data_dir=data_dir, updates_dir=cfg.root / ua.updates_dir,
        registry=ModelRegistry(data_dir / "models"),
        memory=MemoryStore(data_dir / "memory", short_cap=ua.short_term_notes,
                           long_cap=ua.long_term_notes, refresh_days=ua.long_term_refresh_days),
        tolerance=ua.gate_tolerance, max_retries=ua.max_guard_retries,
        refit_fn=train_and_forecast, latest_month_fn=default_latest_months,
        collect_fn=collect, agent_fn=write_update,
    )
