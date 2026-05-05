"""Exposure dashboard — current % NAV by asset class + by instrument."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from castelino.config import get_settings
from castelino.execution.portfolio import Portfolio


def generate() -> list[Path]:
    cfg = get_settings()
    out_dir = cfg.resolved_paths.reports
    out_dir.mkdir(parents=True, exist_ok=True)
    pf = Portfolio.load()
    nav = pf.nav

    out: list[Path] = []
    if nav <= 0:
        return out

    out.append(_plot_class_exposure(pf, out_dir))
    out.append(_plot_instrument_exposure(pf, out_dir))
    return out


def _plot_class_exposure(pf: Portfolio, out_dir: Path) -> Path:
    by_class = pf.exposure_by_class()
    nav = pf.nav
    classes = [c.value for c in by_class]
    pcts = [v / nav * 100 for v in by_class.values()]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(classes, pcts, color="#3fb950")
    ax.set_title("Gross Exposure by Asset Class (% NAV)")
    ax.set_ylabel("% NAV")
    ax.axhline(40, color="red", linestyle="--", linewidth=1, label="40% cap")
    ax.legend()
    for bar, pct in zip(bars, pcts, strict=False):
        if pct > 0.0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f"{pct:.1f}%", ha="center", fontsize=9)
    ax.grid(alpha=0.2, axis="y")
    fig.tight_layout()
    p = out_dir / "exposure_by_class.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    return p


def _plot_instrument_exposure(pf: Portfolio, out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4))
    if not pf.positions:
        ax.text(0.5, 0.5, "No open positions", ha="center", va="center")
        ax.axis("off")
    else:
        names = [p.instrument_id for p in pf.positions]
        values = [p.market_value / pf.nav * 100 for p in pf.positions]
        colors = ["#1f6feb" if v >= 0 else "#d1242f" for v in values]
        ax.barh(names, values, color=colors)
        ax.set_title("Net Exposure by Instrument (% NAV)")
        ax.set_xlabel("% NAV (signed)")
        ax.axvline(0, color="black", linewidth=0.5)
        ax.axvline(5, color="red", linestyle="--", linewidth=1)
        ax.axvline(-5, color="red", linestyle="--", linewidth=1)
        ax.grid(alpha=0.2, axis="x")
    fig.tight_layout()
    p = out_dir / "exposure_by_instrument.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    return p
