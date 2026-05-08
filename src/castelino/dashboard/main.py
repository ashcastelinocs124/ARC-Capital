"""Dashboard backend for CKM Capital.

Serves both the OpenBB Workspace integration (widgets.json + apps.json) and
the custom React frontend at frontend/dist/ when built.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="CKM Capital — Dashboard Backend")

# CORS: OpenBB Workspace + Vite dev server on :5173
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pro.openbb.co",
        "https://pro.openbb.dev",
        "http://localhost:1420",
        "http://localhost:5173",  # Vite dev
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_DIR = Path(__file__).parent
_REPO_ROOT = _DIR.parent.parent.parent
_FRONTEND_DIST = _REPO_ROOT / "frontend" / "dist"

WIDGETS = json.loads((_DIR / "widgets.json").read_text())
APPS = json.loads((_DIR / "apps.json").read_text())


@app.get("/widgets.json")
def get_widgets():
    return WIDGETS


@app.get("/apps.json")
def get_apps():
    return APPS


from castelino.dashboard.endpoints import agents, approvals, macro, portfolio, research, risk  # noqa: E402
from castelino.dashboard.endpoints import personas as personas_router  # noqa: E402

app.include_router(portfolio.router)
app.include_router(macro.router)
app.include_router(research.router)
app.include_router(risk.router)
app.include_router(agents.router)
app.include_router(approvals.router)
app.include_router(personas_router.router)


# ── Frontend static files ──────────────────────────────────────────────────
# When the React app has been built (`cd frontend && npm run build`), serve it
# at the root URL. Production users hit a single port. In dev, run Vite at
# :5173 and let it proxy /api to this backend.

if _FRONTEND_DIST.exists():
    # Mount the assets directory (JS/CSS bundles)
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

    # SPA fallback: any non-API route serves index.html so React Router takes over.
    @app.get("/", include_in_schema=False)
    def serve_index():
        return FileResponse(str(_FRONTEND_DIST / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Don't intercept API calls — they're already routed above.
        target = _FRONTEND_DIST / full_path
        if target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))

else:
    @app.get("/")
    def root():
        return {
            "name": "CKM Capital",
            "status": "running",
            "frontend": "not built — run `cd frontend && npm run build`",
        }
