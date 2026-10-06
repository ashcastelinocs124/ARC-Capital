"""Run one live adoption period against SEC, the job boards and yfinance.

Shared by `ckm adoption run` and the dashboard Refresh button.
"""

from __future__ import annotations

from datetime import date

from castelino.adoption import pipeline, universe
from castelino.adoption.extract import extract_claims
from castelino.adoption.sources.edgar import EdgarClient
from castelino.adoption.sources.financials import fetch_financials
from castelino.adoption.sources.jobs import JobsFetcher, load_boards
from castelino.adoption.store import AdoptionStore
from castelino.config import get_settings


def run_live(period: str | None = None, store: AdoptionStore | None = None) -> pipeline.RunSummary:
    """Raises ValueError (before any network call) when config or the universe file is missing."""
    cfg = get_settings()
    a = cfg.adoption
    if not a.sec_user_agent.strip():
        raise ValueError(
            "set adoption.sec_user_agent in config.yaml (SEC requires a contact string)"
        )
    try:
        _ = cfg.openai_api_key  # raises when the key is missing
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"OpenAI key unavailable: {e}") from e
    d = cfg.root / a.data_dir
    upath = d / "universe.csv"
    if not upath.exists():
        raise ValueError(f"missing {upath}; run `ckm adoption universe-refresh` first")

    edgar = EdgarClient(a.sec_user_agent, min_interval=a.request_interval_s)
    boards = d / "job_boards.csv"
    jobs = JobsFetcher(load_boards(boards) if boards.exists() else {}, recipes_dir=d / "recipes")
    deps = pipeline.Deps(
        companies=universe.load_universe(upath),
        filing_for=edgar.latest_filing,
        text_for=edgar.filing_text,
        extract=lambda t, text: extract_claims(
            t, text, max_passages=a.max_passages, window=a.passage_window_chars
        ),
        jobs_for=jobs.counts,
        financials_for=fetch_financials,
        store=store or AdoptionStore(),
        smoothing_periods=a.hire_smoothing_periods,
        thin_below=a.thin_cell_below,
    )
    return pipeline.run_period(period or date.today().isoformat(), deps)
