"""Markdown + JSON report writer for the backtest regression suite."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from castelino.backtest_regression.models import CaseResult


def write_report(results: list[CaseResult], *, base_dir: Path | None = None) -> Path:
    """Write a markdown summary + raw JSON dump under `<base_dir>/<timestamp>/`.

    Returns the timestamp directory so the caller can print its path.
    """
    base_dir = Path(base_dir) if base_dir is not None else Path("data/backtest_runs")
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = base_dir / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    by_component: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_component[r.component].append(r)

    lines: list[str] = [f"# Backtest Regression — {ts}", ""]
    if not results:
        lines.append("_No results._")
    else:
        for component, items in sorted(by_component.items()):
            passed = sum(r.passed for r in items)
            lines.append(f"## {component} — {passed}/{len(items)} passed")
            lines.append("")
            for r in items:
                mark = "✅" if r.passed else "❌"
                note = f" — {r.notes}" if r.notes else ""
                lines.append(f"- {mark} `{r.case_id}`{note}")
            lines.append("")

    (out_dir / "report.md").write_text("\n".join(lines))
    (out_dir / "results.json").write_text(
        json.dumps([r.model_dump() for r in results], indent=2)
    )
    return out_dir
