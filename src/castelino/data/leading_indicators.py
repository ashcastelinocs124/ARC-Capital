"""Macro leading-indicator catalog loaded from `data/macro_leading_indicators.yaml`.

Used by Current Event and Macro Hypothesis agents so the LLM maps headlines to
the same canonical indicator keys the team defined.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from castelino.config import ROOT

_CATALOG_PATH = ROOT / "data" / "macro_leading_indicators.yaml"


@lru_cache
def load_leading_indicator_catalog() -> dict[str, Any]:
    if not _CATALOG_PATH.is_file():
        return {"version": 0, "indicators": []}
    with _CATALOG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def format_catalog_for_prompt() -> str:
    """Markdown block embedded in agent system prompts."""
    doc = load_leading_indicator_catalog()
    rows: list[str] = [
        "## Canonical macro indicators (leading / forward-looking)",
        "",
        "Each line is one catalog entry. When headlines clearly implicate an "
        "indicator, you may emit a `LeadingIndicatorRead` with `indicator_key` "
        "exactly equal to the key in backticks.",
        "",
    ]
    for row in doc.get("indicators", []):
        key = row.get("key", "")
        name = row.get("name", "")
        timing = row.get("timing", "")
        cadence = row.get("typical_cadence", "")
        signal = row.get("what_it_signals", "")
        rows.append(
            f"- `{key}` — **{name}** ({timing}; {cadence}). {signal}"
        )
    rows.append("")
    rows.append(
        f"Total indicators defined: {len(doc.get('indicators', []))}. "
        "Do not invent new `indicator_key` strings."
    )
    return "\n".join(rows)
