"""Freeze the dashboard API into JSON files for the public, read-only Vercel build.

Runs the Refresh-button jobs (unless --no-refresh; --jobs=a,b runs only those), then calls every GET endpoint the
frontend uses through FastAPI's TestClient and writes each response to
frontend/public/api/<path>.json, where the VITE_STATIC=1 build reads it (api/client.ts).
Usage: uv run python scripts/export_snapshot.py [--no-refresh | --jobs=model_refit,cross_asset]
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

# The GETs the public pages make.
PATHS = [
    "/macro_indicators",
    "/update/status",
    "/update/latest",
    "/update/history",
    "/weekly/status",
    "/weekly/latest",
    "/weekly/history",
    "/themes/latest",
    "/themes/history",
    "/agents/catalog",
    "/sector_sentiment",
    "/week_ahead",
    "/ai_sentiment",
    "/research",
    "/refresh/status",
    "/videos",
    "/daily_posts",
    "/weekly_posts",
    "/section_posts",
    # private: /api/admin/ is password-gated by frontend/middleware.ts
    "/admin/agents/catalog",
    "/admin/models",  # the models are admin-only since 2026-10-15
    "/admin/adoption/summary",
    "/admin/adoption/companies",
    "/admin/cross_asset",
]


def snapshot_file(path: str) -> Path:
    """Must match staticUrl() in frontend/src/api/client.ts."""
    p, _, qs = path.partition("?")
    suffix = "__" + re.sub(r"[^A-Za-z0-9]+", "_", qs) if qs else ""
    return OUT / f"{p.lstrip('/')}{suffix}.json"


def copy_charts(day: str, rec: dict, updates_dir: Path | None = None) -> int:
    """Morning Note exhibits are PNGs, not JSON: copy them next to the day's snapshot."""
    if updates_dir is None:
        from castelino.config import get_settings

        cfg = get_settings()
        updates_dir = cfg.root / cfg.update_agent.updates_dir
    src = updates_dir / "charts" / day
    n = 0
    for ex in rec.get("exhibits") or []:
        f = src / ex["file"]
        if f.is_file():
            dst = OUT / "update" / day / "charts" / ex["file"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dst)
            n += 1
    return n


def copy_weekly_charts(week: str, rec: dict, deep_dir: Path | None = None) -> int:
    """Weekly Deep Dive exhibits: copy the PNGs next to the week's snapshot."""
    if deep_dir is None:
        from castelino.config import get_settings

        cfg = get_settings()
        deep_dir = cfg.root / cfg.deep_dive.data_dir
    n = 0
    for ex in rec.get("exhibits") or []:
        f = deep_dir / "charts" / week / ex["file"]
        if f.is_file():
            dst = OUT / "weekly" / week / "charts" / ex["file"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dst)
            n += 1
    return n


def copy_theme_charts(run_id: str, rec: dict, themes_dir: Path | None = None) -> int:
    """Theme Charts exhibits: copy the PNGs next to the run's snapshot."""
    if themes_dir is None:
        from castelino.agents.themes import _dir

        themes_dir = _dir()
    n = 0
    for ex in rec.get("exhibits") or []:
        f = themes_dir / "charts" / run_id / ex["file"]
        if f.is_file():
            dst = OUT / "themes" / run_id / "charts" / ex["file"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dst)
            n += 1
    return n


def run_refresh(only: list[str] | None = None) -> None:
    for key, fn in refresh._RUNNERS.items():
        if only and key not in only:
            continue
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
        if re.fullmatch(r"/update/\d{4}-\d{2}-\d{2}", path) and data.get("version") == 2:
            copy_charts(path.rsplit("/", 1)[1], data)
        if re.fullmatch(r"/weekly/\d{4}-W\d{2}", path):
            copy_weekly_charts(path.rsplit("/", 1)[1], data)
        if re.fullmatch(r"/themes/\d{4}-\d{2}-\d{2}-(am|pm)", path):
            copy_theme_charts(path.rsplit("/", 1)[1], data)
        # Fan out to the parameterised GETs the pages make.
        if path == "/update/history":
            queue += [f"/update/{d}" for d in data.get("dates", [])]
        elif path == "/weekly/history":
            queue += [f"/weekly/{i['week']}" for i in data.get("items", [])]
        elif path == "/themes/history":
            queue += [f"/themes/{i['run_id']}" for i in data.get("items", [])]
        elif path == "/research" and isinstance(data, list):
            queue += [f"/research/{row['id']}" for row in data if "id" in row]
        elif path == "/admin/adoption/summary":
            queue += [
                f"/admin/adoption/companies?{urlencode({'sector': c['sector'], 'bucket': c['bucket']})}"
                for c in data.get("cells", [])
            ]
    print(f"[export] wrote {written} files to {OUT}")
    return written


if __name__ == "__main__":
    jobs = next((a[7:].split(",") for a in sys.argv if a.startswith("--jobs=")), None)
    if bad := set(jobs or ()) - set(refresh._RUNNERS):  # a typo in a crontab must not silently skip
        sys.exit(f"unknown --jobs {sorted(bad)}; known: {', '.join(refresh._RUNNERS)}")
    if "--no-refresh" not in sys.argv:
        run_refresh(jobs)
    sys.exit(0 if export() else 1)
