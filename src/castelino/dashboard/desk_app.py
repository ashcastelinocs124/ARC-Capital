"""The only app the Fly machine serves to the internet: the admin Daily desk API, password-gated.

Basic auth (any username) against the ADMIN_PASSWORD secret; unset or empty refuses everyone.
The static site forwards /api/admin/live/* here (frontend/vercel.json) after its own middleware
has checked the same password. Run: uvicorn castelino.dashboard.desk_app:app
"""

from __future__ import annotations

import base64
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import Response

from castelino.dashboard.endpoints import admin_desk

app = FastAPI(title="ARC admin desk", docs_url=None, redoc_url=None, openapi_url=None)


def authorized(header: str | None, expected: str | None) -> bool:
    if not expected or not header or not header.startswith("Basic "):
        return False
    try:
        _, _, given = base64.b64decode(header[6:]).decode().partition(":")
    except ValueError:
        return False
    return secrets.compare_digest(given.encode(), expected.encode())


@app.middleware("http")
async def gate(request: Request, call_next):
    if not authorized(request.headers.get("authorization"), os.getenv("ADMIN_PASSWORD")):
        return Response(
            "Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="ARC admin"', "Cache-Control": "no-store"},
        )
    return await call_next(request)


app.include_router(admin_desk.router)
