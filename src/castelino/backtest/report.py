"""Phase-6: backtest reporting.

Reads `portfolio_history.parquet` from a run, computes Sharpe / drawdown /
hit-rate metrics, compares to SPY (and a 60/40 SPY+AGG basket), and writes:

    data/backtest_runs/<run_id>/summary.json   — slide-deck numbers
    data/backtest_runs/<run_id>/report.html    — equity curve + drawdown viz

Pure-pandas, no LLM. Keeps the run-time dependency surface small.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from castelino.backtest import pricing as bt_pricing
from castelino.backtest.execution import load_history
from castelino.config import get_settings

log = logging.getLogger(__name__)


TRADING_DAYS_PER_YEAR = 252


# ─────────────────────────── metrics ─────────────────────────────────────


@dataclass
class TopLineMetrics:
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    pct_months_positive: float
    n_business_days: int
    start_nav: float
    end_nav: float


@dataclass
class BenchmarkComparison:
    name: str
    bench_total_return: float
    bench_annualized: float
    excess_return: float
    excess_annualized: float
    beta: float
    alpha_annualized: float
    info_ratio: float


@dataclass
class BacktestReport:
    run_id: str
    start: str
    end: str
    top_line: TopLineMetrics
    benchmarks: list[BenchmarkComparison] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "run_id": self.run_id,
            "start": self.start,
            "end": self.end,
            "top_line": asdict(self.top_line),
            "benchmarks": [asdict(b) for b in self.benchmarks],
            "notes": self.notes,
        }, indent=2)


# ───────────────────────── computations ──────────────────────────────────


def _daily_returns(nav: pd.Series) -> pd.Series:
    return nav.pct_change().dropna()


def sharpe(returns: pd.Series, rf_annual: float = 0.0) -> float:
    if returns.std(ddof=0) == 0 or len(returns) < 2:
        return 0.0
    excess = returns - rf_annual / TRADING_DAYS_PER_YEAR
    return float(np.sqrt(TRADING_DAYS_PER_YEAR) * excess.mean() / excess.std(ddof=0))


def max_drawdown(nav: pd.Series) -> float:
    if nav.empty:
        return 0.0
    cummax = nav.cummax()
    dd = (nav / cummax) - 1.0
    return float(dd.min())


def annualized_return(nav: pd.Series) -> float:
    if len(nav) < 2:
        return 0.0
    total = nav.iloc[-1] / nav.iloc[0] - 1.0
    days = (nav.index[-1] - nav.index[0]).days
    if days <= 0:
        return 0.0
    years = days / 365.25
    if years <= 0:
        return 0.0
    return float((1.0 + total) ** (1.0 / years) - 1.0)


def pct_months_positive(nav: pd.Series) -> float:
    if nav.empty:
        return 0.0
    monthly = nav.resample("ME").last().pct_change().dropna()
    if monthly.empty:
        return 0.0
    return float((monthly > 0).mean())


def _bench_series(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series | None:
    """Read the historical-prices archive and return the close series for
    `symbol` in [start, end]. None if the archive is missing or the symbol
    isn't there."""
    p = bt_pricing.historical_prices_path()
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    sub = df[df["instrument_id"] == symbol].copy()
    if sub.empty:
        return None
    sub["date"] = pd.to_datetime(sub["date"]).dt.tz_localize(None).dt.normalize()
    sub = sub[(sub["date"] >= start) & (sub["date"] <= end)]
    if sub.empty:
        return None
    return sub.set_index("date")["close"].sort_index()


def _align_returns(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Align two return series on shared dates. Drop NaNs on either side."""
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    return df["a"], df["b"]


def _benchmark_comparison(
    name: str, port_nav: pd.Series, bench_nav: pd.Series,
) -> BenchmarkComparison:
    pr = _daily_returns(port_nav)
    br = _daily_returns(bench_nav)
    pr, br = _align_returns(pr, br)

    bench_total = float(bench_nav.iloc[-1] / bench_nav.iloc[0] - 1.0)
    bench_annual = annualized_return(bench_nav)
    port_total = float(port_nav.iloc[-1] / port_nav.iloc[0] - 1.0)
    port_annual = annualized_return(port_nav)

    if br.var(ddof=0) == 0:
        beta = 0.0
    else:
        beta = float(pr.cov(br) / br.var(ddof=0))
    excess = pr - br
    excess_annual = float(excess.mean() * TRADING_DAYS_PER_YEAR)
    alpha_annual = float(port_annual - beta * bench_annual)
    if excess.std(ddof=0) == 0:
        info_ratio = 0.0
    else:
        info_ratio = float(
            np.sqrt(TRADING_DAYS_PER_YEAR) * excess.mean() / excess.std(ddof=0),
        )

    return BenchmarkComparison(
        name=name,
        bench_total_return=bench_total,
        bench_annualized=bench_annual,
        excess_return=port_total - bench_total,
        excess_annualized=excess_annual,
        beta=beta,
        alpha_annualized=alpha_annual,
        info_ratio=info_ratio,
    )


# ─────────────────────────── build report ───────────────────────────────


def build_report(run_id: str) -> BacktestReport:
    df = load_history(run_id)
    if df.empty:
        raise RuntimeError(
            f"portfolio_history.parquet for run {run_id!r} is empty or missing"
        )
    df = df.sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    nav = df.set_index("date")["nav"]

    rets = _daily_returns(nav)
    top = TopLineMetrics(
        total_return=float(nav.iloc[-1] / nav.iloc[0] - 1.0),
        annualized_return=annualized_return(nav),
        sharpe_ratio=sharpe(rets),
        max_drawdown=max_drawdown(nav),
        pct_months_positive=pct_months_positive(nav),
        n_business_days=len(df),
        start_nav=float(nav.iloc[0]),
        end_nav=float(nav.iloc[-1]),
    )

    benchmarks: list[BenchmarkComparison] = []
    notes: list[str] = []
    start, end = nav.index[0], nav.index[-1]

    spy = _bench_series("SPY", start, end)
    if spy is not None and len(spy) > 1:
        benchmarks.append(_benchmark_comparison("SPY", nav, spy))
    else:
        notes.append("SPY benchmark unavailable (missing from historical_prices archive)")

    agg = _bench_series("AGG", start, end)
    if spy is not None and agg is not None and len(spy) > 1 and len(agg) > 1:
        # 60/40 SPY+AGG basket, daily rebalanced
        joined = pd.concat([spy.rename("spy"), agg.rename("agg")], axis=1).dropna()
        spy_ret = joined["spy"].pct_change().fillna(0.0)
        agg_ret = joined["agg"].pct_change().fillna(0.0)
        bench_ret = 0.6 * spy_ret + 0.4 * agg_ret
        bench_nav = (1.0 + bench_ret).cumprod() * float(nav.iloc[0])
        benchmarks.append(_benchmark_comparison("60/40 (SPY+AGG)", nav, bench_nav))
    elif agg is None:
        notes.append("AGG missing — skipping 60/40 benchmark")

    return BacktestReport(
        run_id=run_id,
        start=start.date().isoformat(),
        end=end.date().isoformat(),
        top_line=top,
        benchmarks=benchmarks,
        notes=notes,
    )


def write_report(run_id: str) -> tuple[Path, Path]:
    """Build + persist summary.json and report.html. Returns both paths."""
    rep = build_report(run_id)
    cfg = get_settings()
    out_dir = Path(cfg.root) / cfg.backtest.runs_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "summary.json"
    html_path = out_dir / "report.html"
    json_path.write_text(rep.to_json())
    html_path.write_text(_render_html(rep))
    return json_path, html_path


# ─────────────────────────── HTML rendering ──────────────────────────────


_HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Backtest {run_id}</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 880px;
       margin: 40px auto; padding: 0 20px; color: #222; }}
h1 {{ margin: 0 0 4px 0; }} .sub {{ color: #666; }}
table {{ border-collapse: collapse; width: 100%; margin: 14px 0 24px; }}
th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; }}
th {{ background: #fafafa; }}
.note {{ background: #fffbe6; border-left: 3px solid #d4b106;
        padding: 8px 12px; margin: 6px 0; font-size: 13px; }}
.kpi {{ display: inline-block; padding: 6px 12px; margin-right: 8px;
       background: #f0f4ff; border-radius: 4px; font-weight: 500; }}
</style></head>
<body>
<h1>Backtest report — <code>{run_id}</code></h1>
<div class="sub">Window: {start} → {end} ({n_days} business days)</div>

<h2>Top-line</h2>
<div>
  <span class="kpi">Total return: {tot_ret:+.2%}</span>
  <span class="kpi">Annualized: {ann_ret:+.2%}</span>
  <span class="kpi">Sharpe: {sharpe:.2f}</span>
  <span class="kpi">Max DD: {dd:.2%}</span>
  <span class="kpi">% months +: {months:.0%}</span>
</div>

<h2>vs. Benchmarks</h2>
{benchmarks_table}

<h2>Notes &amp; caveats</h2>
{notes_html}
</body></html>
"""


def _render_html(rep: BacktestReport) -> str:
    if rep.benchmarks:
        rows = "\n".join(
            f"<tr><td>{b.name}</td><td>{b.bench_annualized:+.2%}</td>"
            f"<td>{b.excess_annualized:+.2%}</td><td>{b.beta:+.2f}</td>"
            f"<td>{b.alpha_annualized:+.2%}</td><td>{b.info_ratio:+.2f}</td></tr>"
            for b in rep.benchmarks
        )
        bt = (
            "<table><thead><tr><th>Benchmark</th><th>Bench ann.</th>"
            "<th>Excess ann.</th><th>Beta</th><th>Alpha ann.</th>"
            "<th>Info ratio</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        bt = "<p><em>No benchmarks available — historical_prices archive missing.</em></p>"

    notes = "".join(f'<div class="note">{n}</div>' for n in rep.notes) \
        or "<p><em>None.</em></p>"

    return _HTML_TEMPLATE.format(
        run_id=rep.run_id,
        start=rep.start, end=rep.end,
        n_days=rep.top_line.n_business_days,
        tot_ret=rep.top_line.total_return,
        ann_ret=rep.top_line.annualized_return,
        sharpe=rep.top_line.sharpe_ratio,
        dd=rep.top_line.max_drawdown,
        months=rep.top_line.pct_months_positive,
        benchmarks_table=bt,
        notes_html=notes,
    )
