"""Freeze the dashboard API into JSON files for the public, read-only Vercel build.

Runs the Refresh-button jobs (unless --no-refresh), then calls every GET endpoint the
frontend uses through FastAPI's TestClient and writes each response to
frontend/public/api/<path>.json, where the VITE_STATIC=1 build reads it (api/client.ts).
Usage: uv run python scripts/export_snapshot.py [--no-refresh]
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from castelino.dashboard.endpoints import refresh
from castelino.dashboard.main import app

OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "api"

# Exactly the GETs in frontend/src/api/*.ts and pages. Approvals, personas and rooms are left
# out on purpose: those pages are gone and their data is internal.
PATHS = [
    "/portfolio_metrics", "/positions", "/equity_curve_chart", "/recent_fills",
    "/models", "/regime_forecast", "/macro_indicators", "/yield_curve_chart",
    "/triggers_table", "/hypotheses_table", "/news_feed", "/econ_calendar",
    "/ta_chart", "/screener", "/correlation_heatmap", "/sector_perf",
    "/exposure_class_chart", "/exposure_instrument_chart", "/warnings_table",
    "/verdicts_table", "/guard_decisions", "/agent_summary", "/agent_triggers",
    "/agent_world_state", "/agent_hypotheses", "/agent_expressions", "/agent_research",
    "/agent_bull", "/agent_bear", "/agent_verdicts", "/agent_guard", "/agent_warnings",
    "/agent_curator", "/update/status", "/update/latest", "/update/history",
    "/agents/catalog", "/sector_sentiment", "/adoption/summary", "/adoption/companies",
    "/research", "/refresh/status",
]


def snapshot_file(path: str) -> Path:
    """Must match staticUrl() in frontend/src/api/client.ts."""
    p, _, qs = path.partition("?")
    suffix = "__" + re.sub(r"[^A-Za-z0-9]+", "_", qs) if qs else ""
    return OUT / f"{p.lstrip('/')}{suffix}.json"


def run_refresh() -> None:
    for key, fn in refresh._RUNNERS.items():
        try:
            print(f"[refresh] {key}: {fn()}")
        except refresh.Skipped as e:
            print(f"[refresh] {key}: skipped ({e})")
        except Exception as e:  # noqa: BLE001 - publish whatever data exists
            print(f"[refresh] {key}: FAILED {e}", file=sys.stderr)


def export() -> int:
    client = TestClient(app)
    shutil.rmtree(OUT, ignore_errors=True)
    queue, written = list(PATHS), 0
    while queue:
        path = queue.pop(0)
        r = client.get(path)
        # Missing file → static 404 → client shows the empty state. Non-JSON 200s are the
        # SPA fallback in dashboard/main.py answering an unknown path once frontend/dist exists.
        if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
            print(f"[export] {path}: HTTP {r.status_code}, skipped")
            continue
        data = r.json()
        f = snapshot_file(path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data))
        written += 1
        # Fan out to the parameterised GETs the pages make.
        if path == "/update/history":
            queue += [f"/update/{d}" for d in data.get("dates", [])]
        elif path == "/research" and isinstance(data, list):
            queue += [f"/research/{row['id']}" for row in data if "id" in row]
        elif path == "/adoption/summary":
            queue += [
                f"/adoption/companies?{urlencode({'sector': c['sector'], 'bucket': c['bucket']})}"
                for c in data.get("cells", [])
            ]
    print(f"[export] wrote {written} files to {OUT}")
    return written


if __name__ == "__main__":
    if "--no-refresh" not in sys.argv:
        run_refresh()
    sys.exit(0 if export() else 1)
