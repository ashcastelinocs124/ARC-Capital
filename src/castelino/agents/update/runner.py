from __future__ import annotations

import asyncio
import json
import logging
import shutil
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from castelino.agents.update.fsio import acquire_lock, atomic_write_text, release_lock
from castelino.agents.update.guard import check_note, clean_picks
from castelino.agents.update.memory import MemoryStore
from castelino.agents.update.models import (
    AgentOutput,
    Briefs,
    DailyRecordV2,
    Exhibit,
    Fact,
    Finding,
    MarketSnapshot,
    MorningNote,
    Review,
    Stage,
)

log = logging.getLogger(__name__)
_STALE_LOCK_SECONDS = 30 * 60
AGENTS = ("macro", "news", "alt", "ai")
MIN_FINDINGS = 3

AgentFn = Callable[[str, str | None], AgentOutput]
# (findings, facts, day, updates_dir) -> (findings with background ids linked, facts, data gaps)
BackgroundFn = Callable[
    [list[Finding], list[Fact], str, Path], tuple[list[Finding], list[Fact], list[str]]
]


def read_status(data_dir: Path) -> dict:
    p = Path(data_dir) / "status.json"
    try:
        st = json.loads(p.read_text())
        if isinstance(st, dict) and "stage" in st:
            return st
    except (OSError, json.JSONDecodeError):
        pass
    return {"stage": Stage.IDLE.value}


class UpdateRunner:
    """Orchestrator → Macro/News/Alt (parallel, ≤ max_rounds follow-ups) → Editor → guard → charts."""

    def __init__(
        self,
        *,
        data_dir: Path,
        updates_dir: Path,
        memory: MemoryStore,
        max_rounds: int,
        max_retries: int,
        max_items: int,
        plan_fn: Callable[[str, str, str], Briefs],
        review_fn: Callable[[list[Finding], int], Review],
        agent_fns: dict[str, AgentFn],
        editor_fn: Callable[[list[Finding], list[Fact], str, str, list[str] | None], MorningNote],
        chart_fn: Callable[[MorningNote, list[Finding], list[Fact], Path], list[Exhibit]],
        today_fn: Callable[[], date] = date.today,
        background_fn: BackgroundFn | None = None,
    ):
        self.data_dir, self.updates_dir = Path(data_dir), Path(updates_dir)
        self.memory = memory
        self.max_rounds, self.max_retries, self.max_items = max_rounds, max_retries, max_items
        self.plan_fn, self.review_fn, self.agent_fns = plan_fn, review_fn, agent_fns
        self.editor_fn, self.chart_fn, self.today_fn = editor_fn, chart_fn, today_fn
        self.background_fn = background_fn
        self._day = ""
        self._gaps: list[str] = []

    # ── status + lock ──────────────────────────────────────────────────────
    def _set(self, stage: Stage, error: str | None = None) -> None:
        atomic_write_text(
            self.data_dir / "status.json",
            json.dumps({"stage": stage.value, "date": self._day, "error": error}),
        )

    def _acquire(self) -> bool:
        return acquire_lock(self.data_dir, _STALE_LOCK_SECONDS)

    def _release(self) -> None:
        release_lock(self.data_dir)

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
    def _gather(self, jobs: dict[str, tuple[str, str | None]]) -> dict[str, AgentOutput]:
        async def one(name: str, brief: str, ask: str | None) -> AgentOutput | None:
            try:
                return await asyncio.to_thread(self.agent_fns[name], brief, ask)
            except Exception as exc:  # noqa: BLE001 — one agent must not sink the note
                log.warning("%s agent failed", name, exc_info=True)
                self._gaps.append(f"{name} agent failed: {str(exc)[:120]}")
                return None

        async def main() -> list[AgentOutput | None]:
            return await asyncio.gather(*(one(n, *v) for n, v in jobs.items()))

        results = asyncio.run(main())
        return {n: o for n, o in zip(jobs, results, strict=True) if o is not None}

    def _run(self, today: date) -> None:
        self._gaps = []
        mem, long = self.memory.read_short(), self.memory.read_long()

        self._set(Stage.PLANNING)
        briefs = self.plan_fn(mem, long, self._day)
        # kept so the admin Daily desk can re-run an agent on its original brief
        atomic_write_text(
            self.updates_dir / "briefs" / f"{self._day}.json", briefs.model_dump_json(indent=1)
        )

        self._set(Stage.RESEARCHING)
        outputs = self._gather(
            {a: (getattr(briefs, a), None) for a in AGENTS if a in self.agent_fns}
        )
        if not outputs:
            raise RuntimeError("all research agents failed")

        rounds = 0
        while rounds < self.max_rounds:
            self._set(Stage.REVIEWING)
            try:
                review = self.review_fn([f for o in outputs.values() for f in o.findings], rounds)
            except Exception:  # noqa: BLE001 — a broken review just ends the loop
                log.warning("review failed; proceeding", exc_info=True)
                break
            asks = {f.agent: f.ask for f in review.followups if f.agent in self.agent_fns}
            if review.done or not asks:
                break
            rounds += 1
            self._set(Stage.RESEARCHING)
            # a failed follow-up keeps that agent's earlier output (only successes overwrite)
            outputs.update(self._gather({a: (getattr(briefs, a), q) for a, q in asks.items()}))

        findings = [f for o in outputs.values() for f in o.findings]
        facts = [f for o in outputs.values() for f in o.facts]
        if len(findings) < MIN_FINDINGS:
            raise RuntimeError(f"only {len(findings)} findings; need {MIN_FINDINGS}")

        note, exhibits, findings, facts = self._compose(findings, facts, mem, long)

        snap = outputs["macro"].snapshot if "macro" in outputs else None
        self.memory.apply(note, snap or MarketSnapshot(date=self._day), today)
        atomic_write_text(
            self.updates_dir / "raw" / f"{self._day}.json",
            json.dumps([f.model_dump() for f in facts], indent=1),
        )
        record = DailyRecordV2(
            date=self._day,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            findings=findings,
            note=note,
            exhibits=exhibits,
            releases=snap.releases if snap else [],
            rounds=rounds,
            data_gaps=self._gaps + (snap.data_gaps if snap else []),
        )
        # written last: its existence is what marks the day done
        atomic_write_text(self.updates_dir / f"{self._day}.json", record.model_dump_json(indent=2))

    def _compose(
        self, findings: list[Finding], facts: list[Fact], mem: str, long: str
    ) -> tuple[MorningNote, list[Exhibit], list[Finding], list[Fact]]:
        """Background → Editor → guard (with retries) → charts. Raises before touching any file
        if the guard fails. Returns the findings and facts with the background linked in."""
        if self.background_fn is not None:
            try:
                findings, facts, gaps = self.background_fn(
                    findings, facts, self._day, self.updates_dir
                )
                self._gaps += gaps
            except Exception as exc:  # noqa: BLE001 — background is never load-bearing
                log.warning("background step failed; writing without it", exc_info=True)
                self._gaps.append(f"background step failed: {exc}")
        errors: list[str] | None = None
        for _attempt in range(self.max_retries + 1):
            self._set(Stage.WRITING)
            note = self.editor_fn(findings, facts, mem, long, errors)
            self._set(Stage.GUARDING)
            errors = check_note(note, findings, facts, items=self.max_items)
            if not errors:
                break
        if errors:
            raise RuntimeError(f"guard failed: {errors}")

        note = clean_picks(note, findings, facts)
        self._set(Stage.CHARTING)
        exhibits = self.chart_fn(note, findings, facts, self.updates_dir / "charts" / self._day)
        return note, exhibits, findings, facts

    def rebuild(self, day: str) -> str:
        """Rewrite `day`'s note from its stored findings + facts (admin Daily desk).

        Memory is not touched: it already took this day in. The previous record, raw facts and
        charts are copied to hidden-rebuild-<time>/ first; a guard failure leaves the old note in
        place.
        """
        path = self.updates_dir / f"{day}.json"
        old = DailyRecordV2.model_validate_json(path.read_text())
        facts = [
            Fact(**f) for f in json.loads((self.updates_dir / "raw" / f"{day}.json").read_text())
        ]
        backup = self.updates_dir / f"hidden-rebuild-{datetime.now():%Y%m%d-%H%M%S}"
        backup.mkdir(parents=True)
        shutil.copy2(path, backup / path.name)
        if (raw := self.updates_dir / "raw" / f"{day}.json").exists():  # rebuild rewrites it too
            (backup / "raw").mkdir()
            shutil.copy2(raw, backup / "raw" / raw.name)
        if (charts := self.updates_dir / "charts" / day).exists():
            shutil.copytree(charts, backup / "charts" / day)

        self._day = day
        note, exhibits, findings, facts = self._compose(
            old.findings, facts, self.memory.read_short(), self.memory.read_long()
        )
        atomic_write_text(
            self.updates_dir / "raw" / f"{day}.json",
            json.dumps([f.model_dump() for f in facts], indent=1),
        )
        new = old.model_copy(
            update={
                "findings": findings,
                "note": note,
                "exhibits": exhibits,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        atomic_write_text(path, new.model_dump_json(indent=2))
        self._set(Stage.DONE)
        return note.headline


# ── production wiring ──────────────────────────────────────────────────────


def build_default_runner() -> UpdateRunner:
    from castelino.agents.update import (
        ai,
        alt,
        background,
        editor,
        exhibits,
        macro,
        news,
        orchestrator,
    )
    from castelino.config import get_settings

    cfg = get_settings()
    ua = cfg.update_agent
    data_dir = cfg.root / ua.data_dir
    return UpdateRunner(
        data_dir=data_dir,
        updates_dir=cfg.root / ua.updates_dir,
        memory=MemoryStore(
            data_dir / "memory",
            short_cap=ua.short_term_notes,
            long_cap=ua.long_term_notes,
            refresh_days=ua.long_term_refresh_days,
        ),
        max_rounds=ua.max_rounds,
        max_retries=ua.max_guard_retries,
        max_items=ua.items,
        plan_fn=orchestrator.plan,
        review_fn=orchestrator.review,
        agent_fns={"macro": macro.run, "news": news.run, "alt": alt.run, "ai": ai.run},
        editor_fn=editor.write_note,
        chart_fn=exhibits.make_note_exhibits,
        background_fn=background.enrich,
    )
