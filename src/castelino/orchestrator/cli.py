"""Castelino Capital CLI — `castelino <command>`.

Subcommands (M1 through M6):
- `run`      Fire the pipeline once with a manual trigger or news headline.
- `mark`     Run the daily mark loop.
- `watch`    Continuous trigger watcher (M5).
- `report`   Regenerate static reports (M6).
- `replay`   Backfill from historical news / calendar (M6).
- `status`   Print portfolio.json + ST journal counts.
- `seed`     Seed a starter book (scripts/seed_book.py wrapper).
- `reset`    Wipe ST/LT journals + portfolio (demo only).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich import print
from rich.table import Table

from castelino.config import get_settings
from castelino.execution.mark_loop import run_mark_loop
from castelino.execution.portfolio import Portfolio
from castelino.memory import io as memio
from castelino.memory.io import WriterIdentity
from castelino.memory.schemas import TriggerRecord, TriggerSource
from castelino.orchestrator.graph import build_graph
from castelino.orchestrator.state import FundState

app = typer.Typer(help="Castelino Capital — multi-agent macro fund.", no_args_is_help=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@app.command()
def run(
    headline: str = typer.Argument(..., help="Headline / event description that fired the pipeline."),
    significance: float = typer.Option(0.7, help="Trigger significance 0–1."),
    source: str = typer.Option("manual", help="Trigger source: calendar | news | cron_fallback | manual."),
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
    print(f"[green]NAV after mark:[/green] {new_pf.nav:,.2f}")
    print(f"open positions: {len(new_pf.positions)}")
    if fills:
        print(f"[yellow]stop-loss fills: {len(fills)}[/yellow]")
        for f in fills:
            print(f"  - {f.instrument_id}: {f.side.value} {f.quantity} @ {f.fill_price:.4f}")
    if warnings:
        print("[red]warnings:[/red]")
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
    print(table)

    print("[bold]Open positions:[/bold]")
    for p in pf.positions:
        print(
            f"  {p.instrument_id}: qty={p.quantity:+.2f} @ {p.avg_entry_price:.4f} "
            f"now {p.current_price:.4f} unrealized=${p.unrealized_pnl:+,.2f}"
        )

    counts = memio.journal_summary()
    print(f"\n[bold]Short-term journal:[/bold] {sum(counts.values())} entries")
    for kind, n in sorted(counts.items()):
        print(f"  {kind}: {n}")
    print(f"\nLong-term lessons: {len(memio.read_long_term())}")
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
    open_browser: bool = typer.Option(True, "--open/--no-open",
                                      help="Open the dashboard in the default browser."),
    refresh_marks: bool = typer.Option(True, "--refresh-marks/--no-refresh-marks",
                                       help="Re-price every position via live yfinance/FRED."),
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
    print("[blue]Connect in OpenBB Workspace: Settings → Data Connectors → Add http://localhost:"
          f"{port}[/blue]")
    uvicorn.run("castelino.dashboard.main:app", host="0.0.0.0", port=port, reload=reload)


@app.command()
def replay(
    days: int = typer.Option(30, help="Number of days of history to replay."),
):
    """Replay historical triggers to seed memory (M6)."""
    from castelino.triggers.runner import replay_historical

    replay_historical(days=days)


@app.command()
def seed():
    """Seed a starter portfolio for demo purposes."""
    pf = Portfolio.load()
    if pf.positions:
        print("[yellow]Portfolio already has positions; seed skipped.[/yellow]")
        return
    pf.save()
    print(f"[green]Seeded portfolio at ${pf.nav:,.2f} NAV.[/green]")


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
    print(table)


@app.command(name="approve")
def approve_cmd(
    entry_id: str = typer.Argument(..., help="Approval item ID (e.g. H-abc123, V-def456)."),
    state_dir: str = typer.Option(None, help="Override state directory."),
):
    """Approve a pending hypothesis or verdict."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    try:
        item = q.approve(entry_id)
        print(f"[green]Approved:[/green] {item.entry_id} ({item.gate})")
    except KeyError:
        print(f"[red]Not found:[/red] {entry_id}")
        raise typer.Exit(1)


@app.command(name="reject")
def reject_cmd(
    entry_id: str = typer.Argument(..., help="Approval item ID."),
    reason: str = typer.Option("", help="Reason for rejection."),
    state_dir: str = typer.Option(None, help="Override state directory."),
):
    """Reject a pending hypothesis or verdict."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    try:
        item = q.reject(entry_id, reason=reason)
        print(f"[red]Rejected:[/red] {item.entry_id} — {reason or '(no reason)'}")
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
        print(f"  regime={h.regime.value} conviction={h.conviction.value} horizon={h.horizon_days}d")
        print(f"  kill criteria: {[c.description for c in h.kill_criteria]}")

    exps = _get("expressions") or []
    print(f"\n[bold]Expressions ({len(exps)}):[/bold]")
    for e in exps:
        print(f"  - {e.direction.value} {e.instrument_id} size={e.target_size_pct_nav:.4f}")

    verdicts = _get("verdicts") or []
    guards = _get("guard_decisions") or []
    for i, (e, v, g) in enumerate(zip(exps, verdicts, guards, strict=False)):
        print(
            f"\n[bold]Trade {i+1} — {e.instrument_id}:[/bold]\n"
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
        print(f"\n[bold]Post-pipeline NAV:[/bold] ${pf.nav:,.2f}  cash=${pf.cash:,.2f}  positions={len(pf.positions)}")


if __name__ == "__main__":
    app()
