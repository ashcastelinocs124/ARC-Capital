"""`ckm adoption ...` commands for the AI Adoption Index."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich import print as rich_print
from rich.table import Table

from castelino.config import get_settings

app = typer.Typer(help="AI Adoption Index (research metric).", no_args_is_help=True)


def _store():
    from castelino.adoption.store import AdoptionStore

    return AdoptionStore()


def _dir() -> Path:
    cfg = get_settings()
    return cfg.root / cfg.adoption.data_dir


@app.command("universe-refresh")
def universe_refresh() -> None:
    """Rank the seed list by market cap (yfinance) and keep the top N per size bucket."""
    from castelino.adoption import universe as U

    d = _dir()
    seed = d / "universe_seed.csv"
    if not seed.exists():
        raise typer.BadParameter(f"missing {seed} (CSV with columns: ticker,bucket)")
    companies = U.build_universe(U.load_seed(seed), U.yf_info, get_settings().adoption.top_n)
    U.save_universe(d / "universe.csv", companies)
    rich_print(f"[green]saved {len(companies)} companies to {d / 'universe.csv'}[/green]")


@app.command()
def run(period: Optional[str] = typer.Option(None, help="YYYY-MM-DD; defaults to today.")) -> None:
    """Run one bi-weekly period: fetch, extract, score, aggregate, store."""
    cfg = get_settings()
    a = cfg.adoption
    if not a.sec_user_agent.strip():
        raise typer.BadParameter(
            "set adoption.sec_user_agent in config.yaml (SEC requires a contact string)"
        )
    try:
        cfg.openai_api_key
    except Exception as e:  # noqa: BLE001
        raise typer.BadParameter(f"OpenAI key unavailable: {e}")

    from castelino.adoption import pipeline as P
    from castelino.adoption import universe as U
    from castelino.adoption.extract import extract_claims
    from castelino.adoption.sources.edgar import EdgarClient
    from castelino.adoption.sources.financials import fetch_financials
    from castelino.adoption.sources.jobs import JobsFetcher, load_boards

    d = _dir()
    upath = d / "universe.csv"
    if not upath.exists():
        raise typer.BadParameter(f"missing {upath}; run `ckm adoption universe-refresh` first")
    edgar = EdgarClient(a.sec_user_agent, min_interval=a.request_interval_s)
    boards = d / "job_boards.csv"
    jobs = JobsFetcher(load_boards(boards) if boards.exists() else {})
    deps = P.Deps(
        companies=U.load_universe(upath),
        filing_for=edgar.latest_filing,
        extract=lambda t, text: extract_claims(
            t, text, max_passages=a.max_passages, window=a.passage_window_chars
        ),
        jobs_for=jobs.counts,
        financials_for=fetch_financials,
        store=_store(),
        smoothing_periods=a.hire_smoothing_periods,
        thin_below=a.thin_cell_below,
    )
    s = P.run_period(period or date.today().isoformat(), deps)
    rich_print(
        f"[green]{s.period}: scored {s.n_scored}/{s.n_companies}, excluded {s.n_excluded}, "
        f"errors {s.n_errors}[/green]"
    )
    for line in s.errors[:20]:
        rich_print(f"[yellow]  {line}[/yellow]")


@app.command()
def show() -> None:
    """Print the latest period's headline numbers."""
    from castelino.adoption.index import headline

    st = _store()
    periods = st.periods()
    if not periods:
        rich_print("[yellow]No adoption data yet. Run `ckm adoption run`.[/yellow]")
        return
    p = periods[-1]
    table = Table(title=f"AI Adoption Index - {p}")
    table.add_column("metric")
    table.add_column("value", justify="right")
    for k, v in headline(st.cells(p)).items():
        table.add_row(k, "-" if v is None else f"{v:.1f}")
    rich_print(table)
