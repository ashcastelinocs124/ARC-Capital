"""Shared fixture loader for backtest regression tests."""
from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixtures(component_subdir: str) -> list[dict]:
    """Load every JSON file in `fixtures/<component_subdir>/`. Returns
    [] if the subdir is absent."""
    path = FIXTURES_DIR / component_subdir
    if not path.is_dir():
        return []
    out: list[dict] = []
    for f in sorted(path.glob("*.json")):
        out.append(json.loads(f.read_text()))
    return out
