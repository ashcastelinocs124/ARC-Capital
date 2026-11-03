from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from castelino.agents.consultants.models import NoteConsult
from castelino.agents.update.fsio import acquire_lock, atomic_write_text, release_lock
from castelino.agents.update.guard import check_note, clean_picks, drop_views, view_errors
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
# (findings, facts, day) -> (findings and facts with the day's calendar results, its lines)
CalendarFn = Callable[[list[Finding], list[Fact], str], tuple[list[Finding], list[Fact], list[str]]]
# (findings, facts, day) -> (findings and facts with the market sentiment ones, data gaps)
SentimentFn = Callable[
    [list[Finding], list[Fact], str], tuple[list[Finding], list[Fact], list[str]]
]
# (day, updates_dir, create=) -> the topic consultants' input for that day (saved per day, so rebuilds
# reuse it; only the daily run creates it)
ConsultFn = Callable[..., NoteConsult]


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
        plan_fn: Callable[[str, str, str, str], Briefs],
        review_fn: Callable[[list[Finding], int], Review],
        agent_fns: dict[str, AgentFn],
        editor_fn: Callable[
            [list[Finding], list[Fact], str, str, list[str] | None, str], MorningNote
        ],
        chart_fn: Callable[[MorningNote, list[Finding], list[Fact], Path], list[Exhibit]],
        today_fn: Callable[[], date] = date.today,
        background_fn: BackgroundFn | None = None,
        calendar_fn: CalendarFn | None = None,
        sentiment_fn: SentimentFn | None = None,
        consult_fn: ConsultFn | None = None,
        view_max_words: int = 100,
        view_max_figures: int = 2,
    ):
        self.data_dir, self.updates_dir = Path(data_dir), Path(updates_dir)
        self.memory = memory
        self.max_rounds, self.max_retries, self.max_items = max_rounds, max_retries, max_items
        self.plan_fn, self.review_fn, self.agent_fns = plan_fn, review_fn, agent_fns
        self.editor_fn, self.chart_fn, self.today_fn = editor_fn, chart_fn, today_fn
        self.background_fn = background_fn
        self.calendar_fn = calendar_fn
        self.sentiment_fn = sentiment_fn
        self.consult_fn = consult_fn
        self.view_max_words, self.view_max_figures = view_max_words, view_max_figures
        self._consulted: NoteConsult | None = None  # this run's consultant input
        self._calendar: list[str] = []  # the note's "Other news on the calendar today" lines
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

    def _consult(self, create: bool = False) -> NoteConsult:
        """The topic consultants' input for this day, fetched once per run. Only the daily run may
        create it (`create`); a rebuild reloads the day's saved input or gets none, never today's
        theses. Never load-bearing: a failure is a data gap and the note goes out without ARC views."""
        if self._consulted is None:
            self._consulted = NoteConsult()
            if self.consult_fn is not None:
                try:
                    self._consulted = self.consult_fn(self._day, self.updates_dir, create=create)
                except Exception as exc:  # noqa: BLE001
                    log.warning("consultants step failed; writing without them", exc_info=True)
                    self._gaps.append(f"consultants step failed: {exc}")
        return self._consulted

    def _run(self, today: date) -> None:
        self._gaps = []
        self._consulted = None
        mem, long = self.memory.read_short(), self.memory.read_long()

        self._set(Stage.PLANNING)
        briefs = self.plan_fn(mem, long, self._day, self._consult(create=True).watch_md)
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
            calendar=self._calendar,
        )
        # written last: its existence is what marks the day done
        atomic_write_text(self.updates_dir / f"{self._day}.json", record.model_dump_json(indent=2))

    def _compose(
        self,
        findings: list[Finding],
        facts: list[Fact],
        mem: str,
        long: str,
        request_md: str = "",
        charts_dir: Path | None = None,
        merge: Callable[[MorningNote], MorningNote] | None = None,
        known: frozenset[str] = frozenset(),
        context: bool = True,
    ) -> tuple[MorningNote, list[Exhibit], list[Finding], list[Fact]]:
        """Background → Editor → guard (with retries) → charts. Raises before touching any file
        if the guard fails. Returns the findings and facts with the background linked in.
        `request_md` is a desk edit the Editor must make (kept in every retry), `merge` fixes
        up each draft before the guard (the desk puts back what the edit didn't touch), and
        `known` are guard errors the note already had (a figure the editor typed and accepted),
        which don't count again. `charts_dir` defaults to the day's charts. context=False keeps
        the day's saved background, calendar and sentiment facts instead of recomputing them (a
        desk edit: recomputed prices would no longer match the note's figures)."""
        if context and self.background_fn is not None:
            try:
                findings, facts, gaps = self.background_fn(
                    findings, facts, self._day, self.updates_dir
                )
                self._gaps += gaps
            except Exception as exc:  # noqa: BLE001 — background is never load-bearing
                log.warning("background step failed; writing without it", exc_info=True)
                self._gaps.append(f"background step failed: {exc}")
        if context and self.calendar_fn is not None:
            try:
                findings, facts, self._calendar = self.calendar_fn(findings, facts, self._day)
            except Exception as exc:  # noqa: BLE001 — the calendar is never load-bearing
                log.warning("calendar step failed; writing without it", exc_info=True)
                self._gaps.append(f"calendar step failed: {exc}")
        if context and self.sentiment_fn is not None:
            try:
                findings, facts, gaps = self.sentiment_fn(findings, facts, self._day)
                self._gaps += gaps
            except Exception as exc:  # noqa: BLE001 — sentiment is never load-bearing
                log.warning("sentiment step failed; writing without it", exc_info=True)
                self._gaps.append(f"sentiment step failed: {exc}")
        consult = self._consult()
        if consult.facts:  # a rebuild's raw facts already hold them: never twice
            ids = {f.id for f in consult.facts}
            facts = [f for f in facts if f.id not in ids] + consult.facts

        def bad_views(n: MorningNote) -> dict[int, list[str]]:
            return view_errors(
                n,
                facts,
                consult.codes,
                max_words=self.view_max_words,
                max_figures=self.view_max_figures,
            )

        feedback: list[str] | None = None
        errors: list[str] = []
        views: dict[int, list[str]] = {}
        passed: MorningNote | None = None  # the last draft that passed the note's own guard
        for _attempt in range(self.max_retries + 1):
            self._set(Stage.WRITING)
            note = self.editor_fn(
                findings,
                facts,
                mem,
                long,
                feedback,
                consult.prompt_md,
                **({"request_md": request_md} if request_md else {}),
            )
            if merge is not None:
                note = merge(note)
            self._set(Stage.GUARDING)
            errors = [
                e
                for e in check_note(note, findings, facts, items=self.max_items)
                if bare_error(e) not in known
            ]
            views = bad_views(note)
            if not errors:
                passed = note
                if not views:
                    break
            feedback = errors + [f"item {r} ARC view: {'; '.join(e)}" for r, e in views.items()]
        if errors:
            if passed is None:
                raise RuntimeError(f"guard failed: {errors}")
            # a retry asked only for a view's sake broke the note: ship the draft that passed
            note, errors = passed, []
            views = bad_views(note)
        if views:  # a bad ARC view is dropped, never fatal: the note goes out without that box
            note = drop_views(note, set(views))
            self._gaps += [
                f"ARC view dropped on item {r}: {'; '.join(e)}" for r, e in views.items()
            ]
        note = note.model_copy(
            update={
                "items": [
                    it.model_copy(
                        update={
                            "view": it.view.model_copy(
                                update={"topic": consult.names.get(it.view.consultant, "")}
                            )
                        }
                    )
                    if it.view
                    else it
                    for it in note.items
                ]
            }
        )

        note = clean_picks(note, findings, facts)
        self._set(Stage.CHARTING)
        exhibits = self.chart_fn(
            note, findings, facts, charts_dir or self.updates_dir / "charts" / self._day
        )
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
        backup_day(self.updates_dir, day)

        self._day = day
        self._consulted = None  # reload that day's saved consultant input, not today's theses
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
                "calendar": self._calendar or old.calendar,  # a failed fetch keeps the old lines
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "hand_edited_at": None,  # a fresh note: the hand edits are in the backup
            }
        )
        atomic_write_text(path, new.model_dump_json(indent=2))
        self._set(Stage.DONE)
        return note.headline

    def propose(
        self,
        day: str,
        request_md: str,
        charts_dir: Path,
        merge: Callable[[MorningNote], MorningNote] | None = None,
    ) -> tuple[DailyRecordV2, list[Fact]]:
        """`day`'s note rewritten for a desk edit, NOT saved: the desk keeps it as a proposal
        until the editor approves it. Charts are drawn into `charts_dir`. Raises on a guard
        failure, like rebuild; errors the current note already has don't count."""
        old = DailyRecordV2.model_validate_json((self.updates_dir / f"{day}.json").read_text())
        facts = [
            Fact(**f) for f in json.loads((self.updates_dir / "raw" / f"{day}.json").read_text())
        ]
        self._day = day
        self._consulted = None  # that day's saved consultant input, as in rebuild
        known = frozenset(
            bare_error(e) for e in check_note(old.note, old.findings, facts, items=self.max_items)
        )
        note, exhibits, findings, facts = self._compose(
            old.findings,
            facts,
            self.memory.read_short(),
            self.memory.read_long(),
            request_md=request_md,
            charts_dir=charts_dir,
            merge=merge,
            known=known,
            context=False,  # the note's figures come from the day's saved facts: keep them
        )
        self._set(Stage.DONE)
        rec = old.model_copy(
            update={
                "findings": findings,
                "note": note,
                "exhibits": exhibits,
                "calendar": self._calendar or old.calendar,
            }
        )
        return rec, facts


def bare_error(e: str) -> str:
    """A guard error without its item number, so it still matches after the item moves."""
    return re.sub(r"^item \d+: ", "", e)


def backup_day(updates_dir: Path, day: str) -> Path:
    """Copy the day's record, raw facts and charts to hidden-rebuild-<time>/ before a rewrite."""
    path = updates_dir / f"{day}.json"
    backup = updates_dir / f"hidden-rebuild-{datetime.now():%Y%m%d-%H%M%S-%f}"
    backup.mkdir(parents=True)
    shutil.copy2(path, backup / path.name)
    if (raw := updates_dir / "raw" / f"{day}.json").exists():
        (backup / "raw").mkdir()
        shutil.copy2(raw, backup / "raw" / raw.name)
    if (charts := updates_dir / "charts" / day).exists():
        shutil.copytree(charts, backup / "charts" / day)
    return backup


# ── production wiring ──────────────────────────────────────────────────────


def build_default_runner() -> UpdateRunner:
    from castelino.agents.consultants import consult
    from castelino.agents.update import (
        ai,
        alt,
        background,
        calendar,
        editor,
        exhibits,
        macro,
        news,
        orchestrator,
        sentiment,
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
        calendar_fn=calendar.add,
        sentiment_fn=sentiment.add,
        consult_fn=consult.for_note,
        view_max_words=cfg.consultants.view_max_words,
        view_max_figures=cfg.consultants.view_max_figures,
    )
