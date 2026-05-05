"""Equity curve + drawdown PNGs from `nav_history`."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from castelino.config import get_settings
from castelino.execution.portfolio import Portfolio


def generate() -> list[Path]:
    cfg = get_settings()
    out_dir = cfg.resolved_paths.reports
    out_dir.mkdir(parents=True, exist_ok=True)
    pf = Portfolio.load()

    if not pf.nav_history:
        return []

    df = pd.DataFrame(
        [{"timestamp": s.timestamp, "nav": s.nav} for s in pf.nav_history]
    ).set_index("timestamp").sort_index()

    out: list[Path] = []
    out.append(_plot_equity(df, out_dir, pf.initial_nav))
    out.append(_plot_drawdown(df, out_dir))
    return out


def _plot_equity(df: pd.DataFrame, out_dir: Path, initial_nav: float) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(df.index, df["nav"], color="#1f6feb", linewidth=1.6)
    ax.axhline(initial_nav, color="grey", linestyle="--", alpha=0.4, label="Initial NAV")
    ax.set_title("Castelino Capital — Equity Curve")
    ax.set_ylabel("NAV (USD)")
    ax.grid(alpha=0.2)
    ax.legend(loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    p = out_dir / "equity_curve.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    return p


def _plot_drawdown(df: pd.DataFrame, out_dir: Path) -> Path:
    nav = df["nav"]
    peak = nav.cummax()
    dd = (nav - peak) / peak

    fig, ax = plt.subplots(figsize=(10, 3.0))
    ax.fill_between(df.index, dd.values, 0, color="#d1242f", alpha=0.5)
    ax.set_title("Drawdown from peak")
    ax.set_ylabel("Drawdown")
    ax.grid(alpha=0.2)
    fig.autofmt_xdate()
    fig.tight_layout()
    p = out_dir / "drawdown.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    return p
