"""P&L attribution — by asset class, instrument, and parent hypothesis."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from castelino.config import get_settings
from castelino.memory import io as memio
from castelino.memory.schemas import TradeEvent


def _trades_df() -> pd.DataFrame:
    rows = []
    for e in memio.read_short_term():
        if isinstance(e, TradeEvent):
            rows.append({
                "ts": e.timestamp,
                "instrument": e.instrument_id,
                "event_type": e.event_type,
                "realized_pnl": e.realized_pnl,
                "parent_hyp": e.parent_hypothesis_id or "(unknown)",
            })
    return pd.DataFrame(rows)


def generate() -> list[Path]:
    cfg = get_settings()
    out_dir = cfg.resolved_paths.reports
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _trades_df()
    out: list[Path] = []
    if df.empty:
        return out

    out.append(_plot_by_instrument(df, out_dir))
    out.append(_plot_by_hypothesis(df, out_dir))
    return out


def _plot_by_instrument(df: pd.DataFrame, out_dir: Path) -> Path:
    by_inst = df.groupby("instrument")["realized_pnl"].sum().sort_values()
    fig, ax = plt.subplots(figsize=(10, 4))
    colors = ["#3fb950" if v >= 0 else "#d1242f" for v in by_inst.values]
    ax.barh(by_inst.index, by_inst.values, color=colors)
    ax.axvline(0, color="black", linewidth=0.5)
    ax.set_title("Realized P&L by Instrument (USD)")
    ax.set_xlabel("USD")
    ax.grid(alpha=0.2, axis="x")
    fig.tight_layout()
    p = out_dir / "attribution_by_instrument.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    return p


def _plot_by_hypothesis(df: pd.DataFrame, out_dir: Path) -> Path:
    by_hyp = df.groupby("parent_hyp")["realized_pnl"].sum().sort_values()
    fig, ax = plt.subplots(figsize=(10, 4))
    colors = ["#3fb950" if v >= 0 else "#d1242f" for v in by_hyp.values]
    ax.barh(by_hyp.index, by_hyp.values, color=colors)
    ax.axvline(0, color="black", linewidth=0.5)
    ax.set_title("Realized P&L by Parent Hypothesis (USD)")
    ax.set_xlabel("USD")
    ax.grid(alpha=0.2, axis="x")
    fig.tight_layout()
    p = out_dir / "attribution_by_hypothesis.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    return p
