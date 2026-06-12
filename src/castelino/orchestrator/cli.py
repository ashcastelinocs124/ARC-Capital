"""Castelino Capital CLI — `ckm <command>`.

Subcommands (M1 through M6):
- `run`      Fire the pipeline once with a manual trigger or news headline.
- `mark`     Run the daily mark loop.
- `watch`    Continuous trigger watcher (M5).
- `report`   Regenerate static reports (M6).
- `status`   Print portfolio.json + ST journal counts.
- `seed`     Seed a starter book (scripts/seed_book.py wrapper).
- `reset`    Wipe ST/LT journals + portfolio (demo only).
"""

from __future__ import annotations

import logging
import warnings
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich import print as rich_print
from rich.table import Table

# Suppress langchain warnings BEFORE importing anything that triggers
# LangChainPendingDeprecationWarning. The warning fires during
# from langchain_core.load.load import Reviver inside langgraph.
# We import langchain_core first so it adds its "default" filter,
# then insert our "ignore" filter after to take precedence.
import langchain_core  # noqa: F401
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

warnings.simplefilter("ignore", LangChainPendingDeprecationWarning)

from castelino.config import get_settings
from castelino.execution.mark_loop import run_mark_loop
from castelino.execution.portfolio import Portfolio
from castelino.memory import io as memio
from castelino.memory.io import WriterIdentity
from castelino.memory.schemas import TriggerRecord, TriggerSource
from castelino.forecast.regime_sectors import merge_forecast_into_state_kwargs
from castelino.orchestrator.graph import build_graph
from castelino.orchestrator.state import FundState

app = typer.Typer(help="Castelino Capital — multi-agent macro fund.", no_args_is_help=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@app.command()
def run(
    headline: str = typer.Argument(
        ..., help="Headline / event description that fired the pipeline."
    ),
    significance: float = typer.Option(0.7, help="Trigger significance 0–1."),
    source: str = typer.Option(
        "manual", help="Trigger source: calendar | news | cron_fallback | manual."
    ),
    asset_classes: str = typer.Option("", help="Comma-separated asset classes affected."),
):
    """Fire one pipeline pass with a manually-supplied trigger."""
    src = TriggerSource(source)
    trg = TriggerRecord(
        source=src,
        headline=headline,
        significance=significance,
        asset_classes_affected=[a.strip() for a in asset_classes.split(",") if a.strip()],
        one_sentence_reason=headline,
    )
    memio.append_short_term(trg, WriterIdentity.TRIGGER_RUNNER)

    state = FundState(
        trigger=trg,
        recent_headlines=[headline],
        portfolio=Portfolio.load(),
        **merge_forecast_into_state_kwargs(),
    )
    graph = build_graph()
    result = graph.invoke(state)

    _print_run_summary(result)


@app.command()
def mark():
    """Run the daily mark loop."""
    pf = Portfolio.load()
    new_pf, fills, warnings = run_mark_loop(pf)
    new_pf.save()
    rich_print(f"[green]NAV after mark:[/green] {new_pf.nav:,.2f}")
    print(f"open positions: {len(new_pf.positions)}")
    if fills:
        rich_print(f"[yellow]stop-loss fills: {len(fills)}[/yellow]")
        for f in fills:
            print(f"  - {f.instrument_id}: {f.side.value} {f.quantity} @ {f.fill_price:.4f}")
    if warnings:
        rich_print("[red]warnings:[/red]")
        for w in warnings:
            print(f"  - {w}")


@app.command()
def status():
    """Print portfolio + journal summary."""
    pf = Portfolio.load()
    cfg = get_settings()
    table = Table(title="Castelino Capital — Status")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("NAV", f"${pf.nav:,.2f}")
    table.add_row("Initial NAV", f"${pf.initial_nav:,.2f}")
    table.add_row("Cash", f"${pf.cash:,.2f}")
    table.add_row("Gross exposure", f"${pf.gross_exposure:,.2f}")
    table.add_row("Net exposure", f"${pf.net_exposure:,.2f}")
    table.add_row("Open positions", str(len(pf.positions)))
    table.add_row("Realized P&L (cum)", f"${pf.realized_pnl:,.2f}")
    rich_print(table)

    rich_print("[bold]Open positions:[/bold]")
    for p in pf.positions:
        print(
            f"  {p.instrument_id}: qty={p.quantity:+.2f} @ {p.avg_entry_price:.4f} "
            f"now {p.current_price:.4f} unrealized=${p.unrealized_pnl:+,.2f}"
        )

    counts = memio.journal_summary()
    rich_print(f"\n[bold]Short-term journal:[/bold] {sum(counts.values())} entries")
    for kind, n in sorted(counts.items()):
        print(f"  {kind}: {n}")
    rich_print(f"\nLong-term lessons: {len(memio.read_long_term())}")
    print(f"Config root: {cfg.root}")


@app.command()
def watch(
    poll_minutes: int = typer.Option(15, help="Minutes between trigger polls."),
    once: bool = typer.Option(False, help="Run a single watcher pass and exit."),
):
    """Continuous trigger watcher (M5). Polls calendar + news, fires the pipeline."""
    from castelino.triggers.runner import watch_loop  # imported lazily; M5

    watch_loop(poll_minutes=poll_minutes, once=once)


@app.command()
def report():
    """Regenerate all static reports."""
    from castelino.reporting import regenerate_all

    paths = regenerate_all()
    print("[green]Reports written:[/green]")
    for p in paths:
        print(f"  - {p}")


@app.command()
def dashboard(
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the dashboard in the default browser."
    ),
    refresh_marks: bool = typer.Option(
        True,
        "--refresh-marks/--no-refresh-marks",
        help="Re-price every position via live yfinance/FRED.",
    ),
):
    """Render the live position dashboard and open it in a browser."""
    from castelino.reporting import dashboard as dash_mod
    from castelino.reporting import attribution, equity_curve, exposure

    # Make sure the chart PNGs exist so the dashboard's <img> tags resolve.
    equity_curve.generate()
    exposure.generate()
    attribution.generate()
    path = dash_mod.generate(refresh_marks=refresh_marks)
    print(f"[green]Dashboard:[/green] {path}")
    if open_browser:
        import webbrowser

        webbrowser.open(f"file://{path.absolute()}")


@app.command()
def serve(
    port: int = typer.Option(7779, help="Port for the OpenBB backend."),
    reload: bool = typer.Option(False, help="Enable auto-reload for development."),
):
    """Start the OpenBB Workspace dashboard backend."""
    import uvicorn

    print(f"[green]Starting Castelino dashboard on port {port}[/green]")
    print(
        "[blue]Connect in OpenBB Workspace: Settings → Data Connectors → Add http://localhost:"
        f"{port}[/blue]"
    )
    uvicorn.run("castelino.dashboard.main:app", host="0.0.0.0", port=port, reload=reload)


@app.command()
def seed():
    """Seed a starter portfolio for demo purposes."""
    pf = Portfolio.load()
    if pf.positions:
        print("[yellow]Portfolio already has positions; seed skipped.[/yellow]")
        return
    pf.save()
    print(f"[green]Seeded portfolio at ${pf.nav:,.2f} NAV.[/green]")


@app.command("forecast-regime")
def forecast_regime(
    history_start: str = typer.Option("2000-01-01", help="History start date for training."),
    n_lags: int = typer.Option(6, help="Number of monthly lags per series."),
    cv_splits: int = typer.Option(5, help="TimeSeriesSplit folds for walk-forward CV."),
    lead_months: int = typer.Option(
        1, help="Forecast horizon in months. Use 2 when current month's data hasn't been published."
    ),
    save: bool = typer.Option(
        True, "--save/--no-save", help="Persist to data/regime_forecast.json."
    ),
):
    """Train **two independent** XGBoost classifiers (growth + inflation) and print
    next-month MoM direction. Each reads its own indicator list YAML in `data/`."""
    from castelino.forecast.regime import (
        GROWTH_INDICATORS_YAML,
        INFLATION_INDICATORS_YAML,
        IndicatorListConfig,
        TrainingConfig,
        train_and_forecast,
        write_forecast,
    )

    growth_cfg = IndicatorListConfig.from_yaml(GROWTH_INDICATORS_YAML)
    inflation_cfg = IndicatorListConfig.from_yaml(INFLATION_INDICATORS_YAML)
    training = TrainingConfig(
        history_start=history_start,
        n_lags=n_lags,
        cv_splits=cv_splits,
        lead_months=lead_months,
    )

    bundle = train_and_forecast(
        growth_cfg=growth_cfg,
        inflation_cfg=inflation_cfg,
        training_cfg=training,
    )

    def _render(title: str, fc, indicator_yaml) -> Table:
        t = Table(title=title)
        t.add_column("Field")
        t.add_column("Value", justify="right")
        t.add_row("target", f"{fc.target_name}  ({fc.target_id})")
        t.add_row("lead horizon", f"{fc.lead_months} month(s) ahead")
        t.add_row("indicators (incl. target)", ", ".join(fc.indicators_used) or "—")
        t.add_row("indicator list", str(indicator_yaml))
        t.add_row("feature month (last obs)", fc.feature_month)
        t.add_row("target month", fc.target_month)
        t.add_row("history start", fc.history_start)
        t.add_row("training observations", str(fc.n_obs))
        t.add_row("up", f"{fc.up}  (P_up = {fc.prob_up:.2%})")
        if fc.train_metrics is not None:
            m = fc.train_metrics
            t.add_row("OOS accuracy / Brier", f"{m.accuracy:.3f} / {m.brier:.3f}")
        return t

    print(_render("Growth nowcaster (next-month MoM)", bundle.growth, GROWTH_INDICATORS_YAML))
    print()
    print(
        _render("Inflation nowcaster (next-month MoM)", bundle.inflation, INFLATION_INDICATORS_YAML)
    )

    if save:
        out = write_forecast(bundle)
        print(f"[green]Saved:[/green] {out}")


@app.command("forecast-risk")
def forecast_risk():
    """Train the risk-off classifier (P(SPY drawdown >5% next month)) and save."""
    from castelino.forecast.risk_off import train_and_predict

    forecast = train_and_predict()
    table = Table(title="Risk-Off Forecast")
    table.add_column("Field")
    table.add_column("Value", justify="right")
    table.add_row("prob_risk_off", f"{forecast.prob_risk_off:.4f}")
    table.add_row("feature month", forecast.feature_month)
    table.add_row("target month", forecast.target_month)
    table.add_row("as of", forecast.as_of.strftime("%Y-%m-%d %H:%M UTC"))
    table.add_row("model version", forecast.model_version)

    if forecast.prob_risk_off < 0.3:
        tier = "[green]calm — gate passes everything[/green]"
    elif forecast.prob_risk_off < 0.6:
        tier = "[yellow]caution — risk-on cut to 0.5x[/yellow]"
    elif forecast.prob_risk_off < 0.85:
        tier = "[red]danger — risk-on vetoed[/red]"
    else:
        tier = "[magenta]capitulation — contrarian amplify 1.3x[/magenta]"
    table.add_row("gate tier", tier)

    rich_print(table)


def _run_indicator_search(
    *,
    target_kind: str,
    history_start: str,
    n_lags: int,
    cv_splits: int,
    lead_months: int,
    max_indicators: int,
    metric: str,
):
    """Shared core for the growth / inflation search commands."""
    from castelino.forecast.regime import (
        GROWTH_INDICATORS_YAML,
        SOURCE_FRED,
        IndicatorListConfig,
        IndicatorSpec,
        TrainingConfig,
    )
    from castelino.forecast.search import (
        SearchStep,
        greedy_forward_search,
        growth_candidate_pool,
        inflation_candidate_pool,
    )

    if target_kind == "growth":
        target = IndicatorListConfig.from_yaml(GROWTH_INDICATORS_YAML).target
        pool = growth_candidate_pool()
    elif target_kind == "inflation":
        target = IndicatorSpec(
            id="CPIAUCSL",
            source=SOURCE_FRED,
            fred_id="CPIAUCSL",
            name="CPI All Items (SA, level)",
        )
        pool = inflation_candidate_pool()
    else:
        raise typer.BadParameter(f"target_kind must be growth|inflation, got {target_kind!r}")

    training = TrainingConfig(
        history_start=history_start,
        n_lags=n_lags,
        cv_splits=cv_splits,
        lead_months=lead_months,
    )
    print(
        f"[bold]Searching {target_kind} indicators[/bold] — pool size {len(pool)}, "
        f"metric={metric}, lead={lead_months}m, history from {history_start}"
    )

    table = Table(title=f"{target_kind.capitalize()} forward-selection log")
    for col in (
        "step",
        "added",
        "selected",
        "balanced_acc",
        "f1_up",
        "recall_up",
        "f1_dn",
        "recall_dn",
        "precision_up",
        "accuracy",
        "brier",
        "n_test",
    ):
        table.add_column(col)

    def _on_step(step: SearchStep) -> None:
        table.add_row(
            str(step.step),
            step.added or "(self-lags only)",
            ", ".join(step.selected) or "—",
            f"{step.balanced_accuracy:.3f}",
            f"{step.f1_up:.3f}",
            f"{step.recall_up:.3f}",
            f"{step.f1_down:.3f}",
            f"{step.recall_down:.3f}",
            f"{step.precision_up:.3f}",
            f"{step.accuracy:.3f}",
            f"{step.brier:.3f}",
            str(step.n_test),
        )

    result = greedy_forward_search(
        target=target,
        candidates=pool,
        training_cfg=training,
        max_indicators=max_indicators,
        metric=metric,
        on_step=_on_step,
    )
    rich_print(table)

    best = result.best_step
    print(
        f"\n[bold green]Best {target_kind} subset (by {result.metric}):[/bold green]\n"
        f"  step={best.step}\n"
        f"  indicators={best.selected or '— (only self-lags)'}\n"
        f"  balanced_acc={best.balanced_accuracy:.3f}, "
        f"f1_up={best.f1_up:.3f}, recall_up={best.recall_up:.3f}, "
        f"f1_down={best.f1_down:.3f}, recall_down={best.recall_down:.3f}, "
        f"precision_up={best.precision_up:.3f}, accuracy={best.accuracy:.3f}, "
        f"brier={best.brier:.3f}"
    )


@app.command("growth-search")
def growth_search(
    history_start: str = typer.Option("2000-01-01"),
    n_lags: int = typer.Option(6),
    cv_splits: int = typer.Option(5),
    lead_months: int = typer.Option(2),
    max_indicators: int = typer.Option(6),
    metric: str = typer.Option(
        "recall_up",
        help="Growth: recall_up (detect MoM rise) | balanced_accuracy | f1_up | "
        "precision_up | recall_down | f1_down | precision_down | accuracy | brier",
    ),
):
    """Greedy forward selection of growth indicators (target from growth YAML: ISM PMI CSV).

    Uses only `growth_candidate_pool()` — **does not touch** inflation YAML.
    """
    _run_indicator_search(
        target_kind="growth",
        history_start=history_start,
        n_lags=n_lags,
        cv_splits=cv_splits,
        lead_months=lead_months,
        max_indicators=max_indicators,
        metric=metric,
    )


@app.command("inflation-search")
def inflation_search(
    history_start: str = typer.Option("2000-01-01"),
    n_lags: int = typer.Option(6),
    cv_splits: int = typer.Option(5),
    lead_months: int = typer.Option(2),
    max_indicators: int = typer.Option(6),
    metric: str = typer.Option(
        "balanced_accuracy",
        help="Inflation: balanced_accuracy (default) | f1_down | recall_down | "
        "precision_down | f1_up | recall_up | accuracy | brier",
    ),
):
    """Greedy forward selection of inflation indicators (target: CPIAUCSL).

    Uses only `inflation_candidate_pool()` — **does not touch** growth YAML.
    """
    _run_indicator_search(
        target_kind="inflation",
        history_start=history_start,
        n_lags=n_lags,
        cv_splits=cv_splits,
        lead_months=lead_months,
        max_indicators=max_indicators,
        metric=metric,
    )


@app.command()
def reset(
    yes: bool = typer.Option(False, "--yes", help="Confirm destructive wipe."),
):
    """Wipe journals + portfolio (demo / test environments only)."""
    if not yes:
        print("[red]Refusing to wipe without --yes.[/red]")
        raise typer.Exit(1)
    cfg = get_settings()
    for f in [
        cfg.resolved_paths.data / "portfolio.json",
        cfg.resolved_paths.data / "exposure_snapshot.json",
        cfg.resolved_paths.data / "system_state.json",
    ]:
        if f.exists():
            f.unlink()
    memio.reset_journals(confirm_token="I_KNOW_WHAT_I_AM_DOING")
    print("[green]Wiped journals + portfolio.[/green]")


@app.command()
def queue(
    state_dir: str = typer.Option(None, help="Override state directory (testing)."),
):
    """List pending approval items."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    pending = q.pending()
    if not pending:
        print("[green]No pending approvals.[/green]")
        return
    table = Table(title="Pending Approvals")
    table.add_column("ID")
    table.add_column("Gate")
    table.add_column("Submitted")
    table.add_column("Details")
    for item in pending:
        details = ""
        if "thesis" in item.payload:
            details = item.payload["thesis"][:80]
        elif "instrument" in item.payload:
            details = f"{item.payload.get('instrument')} → {item.payload.get('decision')}"
        table.add_row(item.entry_id, item.gate, item.submitted_at[:19], details)
    rich_print(table)


@app.command(name="approve")
def approve_cmd(
    entry_id: str = typer.Argument(..., help="Approval item ID (e.g. H-abc123, V-def456)."),
    notes: str = typer.Option("", "--notes", "-n", help="Reasoning notes for the approval."),
    state_dir: str = typer.Option(None, help="Override state directory."),
):
    """Approve a pending hypothesis or verdict."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    try:
        item = q.approve(entry_id, notes=notes)
        suffix = f" — {notes}" if notes else ""
        print(f"[green]Approved:[/green] {item.entry_id} ({item.gate}){suffix}")
    except KeyError:
        print(f"[red]Not found:[/red] {entry_id}")
        raise typer.Exit(1)


@app.command(name="reject")
def reject_cmd(
    entry_id: str = typer.Argument(..., help="Approval item ID."),
    reason: str = typer.Option("", help="Reason for rejection."),
    notes: str = typer.Option("", "--notes", "-n", help="Reasoning notes for the rejection."),
    state_dir: str = typer.Option(None, help="Override state directory."),
):
    """Reject a pending hypothesis or verdict."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    try:
        item = q.reject(entry_id, reason=reason or notes, notes=notes or reason)
        print(f"[red]Rejected:[/red] {item.entry_id} — {item.notes or '(no reason)'}")
    except KeyError:
        print(f"[red]Not found:[/red] {entry_id}")
        raise typer.Exit(1)


@app.command(name="edit")
def edit_cmd(
    entry_id: str = typer.Argument(..., help="Approval item ID."),
    thesis: str = typer.Option(None, help="Revised thesis text."),
    state_dir: str = typer.Option(None, help="Override state directory."),
):
    """Edit and approve a pending hypothesis."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    try:
        current = q.get(entry_id)
        payload = current.payload.copy()
        if thesis:
            payload["thesis"] = thesis
        item = q.edit(entry_id, updated_payload=payload)
        print(f"[green]Edited + Approved:[/green] {item.entry_id}")
        print(f"  thesis: {payload.get('thesis', '(unchanged)')}")
    except KeyError:
        print(f"[red]Not found:[/red] {entry_id}")
        raise typer.Exit(1)


# ───────────────────────── helpers ─────────────────────────────────────────


def _print_run_summary(result) -> None:
    """Print the result of a graph invocation as a readable table."""
    state = result if isinstance(result, dict) else result.__dict__

    def _get(key, default=None):
        return state.get(key, default) if isinstance(state, dict) else getattr(state, key, default)

    print("\n[bold cyan]── Pipeline complete ──[/bold cyan]")
    if _get("aborted"):
        print(f"[red]ABORTED:[/red] {_get('abort_reason')}")
        return

    h = _get("hypothesis")
    if h:
        print(f"[bold]Hypothesis:[/bold] {h.thesis}")
        print(
            f"  regime={h.regime.value} conviction={h.conviction.value} horizon={h.horizon_days}d"
        )
        print(f"  kill criteria: {[c.description for c in h.kill_criteria]}")

    exps = _get("expressions") or []
    print(f"\n[bold]Expressions ({len(exps)}):[/bold]")
    for e in exps:
        print(f"  - {e.direction.value} {e.instrument_id} size={e.target_size_pct_nav:.4f}")

    verdicts = _get("verdicts") or []
    guards = _get("guard_decisions") or []
    for i, (e, v, g) in enumerate(zip(exps, verdicts, guards, strict=False)):
        print(
            f"\n[bold]Trade {i + 1} — {e.instrument_id}:[/bold]\n"
            f"  verdict: {v.decision} (mult={v.size_multiplier:.2f}) — {v.decisive_factor}\n"
            f"  guard:   {g.decision} ({len(g.triggered_rules)} rules) — {g.rationale[:120]}"
        )

    fills = _get("fills") or []
    if fills:
        print(f"\n[bold green]Fills:[/bold green] {len(fills)}")
        for f in fills:
            print(
                f"  - {f.instrument_id} {f.side.value} {f.quantity} @ {f.fill_price:.4f}  "
                f"(slip ${f.slippage_cost:.2f}, comm ${f.commission_cost:.2f})"
            )
    else:
        print("\n[yellow]No fills (held / vetoed).[/yellow]")

    pf = _get("portfolio")
    if pf is not None:
        print(
            f"\n[bold]Post-pipeline NAV:[/bold] ${pf.nav:,.2f}  cash=${pf.cash:,.2f}  positions={len(pf.positions)}"
        )


@app.command("persona-refresh")
def persona_refresh(
    speaker: str = typer.Option("powell", help="Speaker id (e.g. powell)."),
    year: int = typer.Option(None, help="Year to scrape; default current."),
):
    """Scrape Fed website and rebuild the rolling-window persona."""
    import asyncio
    import httpx
    from castelino.triggers.figure_deviation.persona import (
        build_persona_from_speeches,
        save_persona,
    )
    from castelino.triggers.figure_deviation.scrapers.fed import fetch_speeches_for_speaker

    cfg = get_settings()
    sp = next((s for s in cfg.speech.speakers if s.id == speaker), None)
    if not sp:
        print(f"[red]Unknown speaker:[/red] {speaker}")
        raise typer.Exit(1)
    yr = year or datetime.now(UTC).year

    async def _run():
        async with httpx.AsyncClient(base_url="https://www.federalreserve.gov", timeout=30) as c:
            speeches = await fetch_speeches_for_speaker(
                speaker_match=sp.full_name.split()[-1],
                year=yr,
                client=c,
            )
        persona = build_persona_from_speeches(
            speaker_id=sp.id,
            full_name=sp.full_name,
            role=sp.role,
            speeches=speeches,
            lexicon_version=cfg.speech.lexicon_version,
            baseline_window_days=cfg.speech.baseline_window_days,
            half_life_months=cfg.speech.half_life_months,
        )
        path = save_persona(persona)
        print(f"[green]Persona saved:[/green] {path}")
        print(
            f"  speeches: {len(persona.speeches_in_window)}  "
            f"mean: {persona.baseline_vector.hawkish_dovish_mean:+.3f}  "
            f"std: {persona.baseline_vector.hawkish_dovish_std:.3f}"
        )

    asyncio.run(_run())


@app.command("speech-test")
def speech_test(
    speaker: str = typer.Option("powell", help="Speaker id."),
    transcript_file: str = typer.Option(
        None,
        help="Path to a transcript .txt file to replay (skip live audio).",
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--live",
        help="Dry-run (default) — print would-be triggers, don't enqueue.",
    ),
):
    """Smoke-test the speech listener: replay a transcript or stub audio,
    score sentences, log any triggers that would have fired (dry-run)
    or push them onto the speech queue (--live)."""
    import asyncio
    from datetime import datetime, UTC
    from pathlib import Path

    from castelino.config import get_settings
    from castelino.triggers.figure_deviation.emitter import SpeechTriggerEmitter
    from castelino.triggers.figure_deviation.persona import load_persona
    from castelino.triggers.figure_deviation.scorer import split_sentences
    from castelino.triggers.figure_deviation.speech_models import SpeechSegment

    cfg = get_settings()
    sp_cfg = next((s for s in cfg.speech.speakers if s.id == speaker), None)
    if not sp_cfg:
        print(f"[red]Unknown speaker:[/red] {speaker}")
        raise typer.Exit(1)

    try:
        persona = load_persona(speaker)
    except FileNotFoundError:
        print(
            f"[red]No persona found for {speaker}.[/red] Run `ckm persona-refresh --speaker {speaker}` first."
        )
        raise typer.Exit(1)

    if transcript_file is None:
        print("[yellow]No --transcript-file given; nothing to replay.[/yellow]")
        raise typer.Exit(0)

    text = Path(transcript_file).read_text()
    sentences = split_sentences(text)
    print(f"[green]Replaying {len(sentences)} sentences for {sp_cfg.full_name}[/green]")

    # Stage A only (no LLM calls in dry-run if no client available — keep it offline-friendly)
    from castelino.agents.base import FakeLLMClient
    from castelino.triggers.figure_deviation.llm_gate import SpeechShiftClassification

    fake = FakeLLMClient()
    fake.register(
        "SpeechShiftClassification",
        lambda system, user: SpeechShiftClassification(
            is_shift=True,
            direction="hawkish",
            magnitude=0.7,
            decisive_phrase="(dry-run stub)",
            rationale="dry-run",
        ),
    )
    em = SpeechTriggerEmitter(
        speaker_id=sp_cfg.id,
        full_name=sp_cfg.full_name,
        baseline=persona.baseline_vector,
        threshold_sigma=cfg.speech.deviation_threshold_sigma,
        llm_client=fake,
        lexicon_version=cfg.speech.lexicon_version,
        window_size=cfg.speech.window_size,
    )
    for s in sentences:
        em.ingest(
            SpeechSegment(
                speaker_id=sp_cfg.id,
                text=s,
                timestamp=datetime.now(UTC),
                event_id=f"speech-test-{speaker}",
            )
        )

    if not em.triggers:
        print("[blue]No triggers fired during replay.[/blue]")
        return
    print(f"[green]Triggers fired: {len(em.triggers)}[/green]")
    for trg in em.triggers:
        print(f"  - {trg.headline} (significance={trg.significance:.2f})")
        print(f"    reason: {trg.one_sentence_reason}")
    if not dry_run:
        from castelino.triggers.figure_deviation.queue import speech_trigger_queue

        for trg in em.triggers:
            speech_trigger_queue.offer(trg)
        print(f"[green]Pushed {len(em.triggers)} trigger(s) onto pipeline queue.[/green]")


@app.command("persona-build")
def persona_build(
    persona_id: str = typer.Option(..., help="Persona id (e.g. buffett)."),
    full_name: str = typer.Option(..., help="Display name."),
    role: str = typer.Option(..., help="Short role label."),
):
    """Scrape primary sources, chunk, embed into Chroma, generate profile card."""
    import asyncio

    from castelino.agents.base import get_llm_client
    from castelino.agents.personas.build import build_persona

    asyncio.run(
        build_persona(
            persona_id=persona_id,
            full_name=full_name,
            role=role,
            client=get_llm_client(),
        )
    )
    print(f"[green]Persona built:[/green] {persona_id}")


@app.command("backtest-regression")
def backtest_regression(
    components: str = typer.Option(
        "risk_off,figure_deviation,materialize_order",
        help="Comma-separated subset of components to run.",
    ),
    out_dir: str = typer.Option(
        "data/backtest_runs",
        help="Where to write the markdown + JSON report.",
    ),
) -> None:
    """Run the deterministic-component regression suite."""
    from castelino.backtest_regression.runner import (
        run_all_risk_off,
        run_all_figure_deviation,
        run_all_materialize_order,
    )
    from castelino.backtest_regression.report import write_report

    requested = {c.strip() for c in components.split(",") if c.strip()}
    results = []
    if "risk_off" in requested:
        results.extend(run_all_risk_off())
    if "figure_deviation" in requested:
        results.extend(run_all_figure_deviation())
    if "materialize_order" in requested:
        results.extend(run_all_materialize_order())

    out = write_report(results, base_dir=Path(out_dir))
    total = len(results)
    passed = sum(r.passed for r in results)
    print(f"[bold]Backtest regression: {passed}/{total} passed[/bold]")
    print(f"Report: {out / 'report.md'}")


@app.command()
def backtest(
    start: str = typer.Option("2023-10-01", help="ISO start date (Oct 2023 = gpt-4o cutoff)."),
    end: str = typer.Option(..., help="ISO end date — usually today."),
    run_id: str = typer.Option(..., help="Unique run id, e.g. 'ckm-bt-2026-05-08-001'."),
    skeleton: bool = typer.Option(
        False,
        help="Skeleton mode — keyword scoring, no LLM calls. Verifies plumbing only.",
    ),
    with_graph: bool = typer.Option(
        False,
        "--with-graph",
        help="Invoke the real LangGraph DAG on every fire (full backtest, ~$60-80, ~6-8h).",
    ),
) -> None:
    """Run the historical backtest harness (gpt-4o, Oct 2023 onwards).

    Three modes:
      --skeleton     keyword scoring + stub fire (no LLM, free, < 1 min)
      (default)      real score_batch + trigger router, stub fire (cheap)
      --with-graph   real graph invocation + mark loop + portfolio snapshots
                     (full backtest — burns gpt-4o credits, ~$60-80 over 30 mo)

    Prerequisites (Phase-1 one-time setup):
      python scripts/build_historical_prices.py
      NYT_API_KEY=... python scripts/build_nyt_archive.py
      python scripts/build_sonar_trump_archive.py     # PERPLEXITY_API_KEY required
    """
    from datetime import date as _date
    from castelino.backtest.runner import BacktestRunner
    from castelino.backtest import integration as ig

    start_d = _date.fromisoformat(start)
    end_d = _date.fromisoformat(end)

    if skeleton:
        print("[cyan]Skeleton mode — keyword scoring, no LLM calls.[/cyan]")
        runner = BacktestRunner()  # uses stub_score / stub_trigger / stub_fire
    elif with_graph:
        print("[bold red]LIVE PIPELINE — real graph + mark loop + portfolio snapshots[/bold red]")
        print("[yellow]This burns gpt-4o credits. Ctrl-C aborts after the current day.[/yellow]")
        from castelino.backtest.execution import (
            PortfolioHolder,
            append_daily_snapshot,
            initial_portfolio,
            make_fire_fn,
            run_daily_mark,
            snapshot_row,
        )

        ig.reset_state()
        holder = PortfolioHolder(initial_portfolio())
        fire_fn = make_fire_fn(holder)

        def _eod(d):
            holder.set(run_daily_mark(holder.get()))
            append_daily_snapshot(run_id, snapshot_row(d, holder.get()))

        runner = BacktestRunner(
            score_fn=ig.real_score_fn,
            trigger_fn=ig.real_trigger_fn,
            fire_fn=fire_fn,
            end_of_day_fn=_eod,
        )
    else:
        print("[cyan]Live triggers, stub fire — score_batch + trigger router only.[/cyan]")
        ig.reset_state()
        runner = BacktestRunner(
            score_fn=ig.real_score_fn,
            trigger_fn=ig.real_trigger_fn,
        )
    summary = runner.run(start=start_d, end=end_d, run_id=run_id)
    print(f"[bold green]Run complete:[/bold green] {run_id}")
    print(f"  Business days: {summary.business_days}")
    print(f"  Total headlines: {summary.total_headlines}")
    print(f"  Pipeline fires: {summary.pipeline_fires}")
    print(f"  Triggers by path: {summary.triggers_by_path}")


@app.command("backtest-report")
def backtest_report_cmd(
    run_id: str = typer.Argument(..., help="Run id of a completed backtest."),
) -> None:
    """Build summary.json + report.html for a completed backtest run."""
    from castelino.backtest.report import write_report

    json_path, html_path = write_report(run_id)
    print(f"[green]summary.json[/green] → {json_path}")
    print(f"[green]report.html[/green]  → {html_path}")


@app.command()
def research(
    query: str = typer.Argument(..., help="Your research question."),
    no_clarify: bool = typer.Option(
        False,
        "--no-clarify",
        help="Skip clarifying questions; auto-assume context.",
    ),
):
    """Run the deep-research engine on a query and print a cited report."""
    from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator

    orch = DeepResearchOrchestrator()

    if no_clarify:
        sess = orch.run_sync(query)
    else:
        sess = orch.start(query)
        if sess.clarifying_questions:
            print(f"[bold]Reworded:[/bold] {sess.reworded_query}\n")
            answers = {}
            for q in sess.clarifying_questions:
                ans = typer.prompt(f"❓ {q.question}")
                answers[q.question] = ans
            sess = orch.run_first_round(sess.id, answers=answers)
        else:
            sess = orch.run_first_round(sess.id, answers={})
        if sess.status.value != "failed":
            sess = orch.finish(sess.id)

    if sess.status.value == "failed":
        print(f"[red]Research failed:[/red] {sess.error}")
        raise typer.Exit(code=1)

    rep = sess.report
    print(f"\n[bold green]Answer[/bold green] (confidence {rep.confidence}):\n")
    print(rep.exec_summary)
    if rep.caveats:
        print("\n[bold]Caveats:[/bold]")
        for c in rep.caveats:
            print(f"  • {c}")
    print("\n[bold]Sources:[/bold]")
    for s in rep.sources:
        print(f"  • {s.title or s.url} — {s.url}")
    charts = getattr(rep, "charts", []) or []
    if charts:
        print("\n[bold]Supporting charts:[/bold]")
        for c in charts:
            n_pts = sum(len(s.points) for s in c.series)
            # Parens, not brackets — rich's print treats [..] as markup tags.
            line = f"  • {c.title} ({c.type.value}, {n_pts} pts)"
            if c.rationale:
                line += f' — "{c.rationale}"'
            print(line)
    print(f"\n[dim]Session {sess.id} saved.[/dim]")


@app.command()
def chat():
    """Interactive natural-language assistant over the fund.

    Read/query/research actions run freely.  Mutating or costly actions are
    confirmed by the human first.
    """
    from castelino.agents.chat.repl import run_repl

    run_repl()


if __name__ == "__main__":
    app()
