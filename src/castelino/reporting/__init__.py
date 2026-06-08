"""Reporting — static HTML / PNG outputs regenerated after every state change.

`regenerate_all()` is the single entry point used by `ckm report`.
"""

from __future__ import annotations

from pathlib import Path

from castelino.config import get_settings


def regenerate_all(refresh_marks: bool = True) -> list[Path]:
    """Run every report generator in order; return the list of output paths."""
    from castelino.reporting import (
        attribution, dashboard, equity_curve, exposure, trade_card,
    )

    cfg = get_settings()
    cfg.resolved_paths.reports.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    paths.extend(equity_curve.generate())
    paths.extend(exposure.generate())
    paths.extend(attribution.generate())
    paths.extend(trade_card.generate())
    paths.append(dashboard.generate(refresh_marks=refresh_marks))
    return paths
