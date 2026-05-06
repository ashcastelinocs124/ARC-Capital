"""OpenBB Workspace backend for Castelino Capital."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Castelino Capital — OpenBB Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pro.openbb.co",
        "https://pro.openbb.dev",
        "http://localhost:1420",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_DIR = Path(__file__).parent
WIDGETS = json.loads((_DIR / "widgets.json").read_text())
APPS = json.loads((_DIR / "apps.json").read_text())


@app.get("/")
def root():
    return {"name": "Castelino Capital", "status": "running"}


@app.get("/widgets.json")
def get_widgets():
    return WIDGETS


@app.get("/apps.json")
def get_apps():
    return APPS


from castelino.dashboard.endpoints import agents, approvals, macro, portfolio, research, risk  # noqa: E402

app.include_router(portfolio.router)
app.include_router(macro.router)
app.include_router(research.router)
app.include_router(risk.router)
app.include_router(agents.router)
app.include_router(approvals.router)
