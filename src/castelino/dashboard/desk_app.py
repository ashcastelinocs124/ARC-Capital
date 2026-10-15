"""The only app the Fly machine serves to the internet: the admin Daily desk API, password-gated.

Accepts either the site's `arc_admin` session cookie (set by frontend/middleware.ts on sign-in, HMAC-SHA256
keyed by ADMIN_PASSWORD) or HTTP Basic auth (any username, for curl). ADMIN_PASSWORD unset or empty refuses
everyone. The static site forwards /api/admin/live/* here (frontend/vercel.json) after its own middleware
has checked the same password. Run: uvicorn castelino.dashboard.desk_app:app
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from http.cookies import CookieError, SimpleCookie

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from castelino.dashboard.endpoints import admin_desk, trade

app = FastAPI(title="ARC admin desk", docs_url=None, redoc_url=None, openapi_url=None)
COOKIE = "arc_admin"


def authorized(header: str | None, expected: str | None) -> bool:
    if not expected or not header or not header.startswith("Basic "):
        return False
    try:
        _, _, given = base64.b64decode(header[6:]).decode().partition(":")
    except ValueError:
        return False
    return secrets.compare_digest(given.encode(), expected.encode())


def session_sig(exp: int, secret: str) -> str:
    """Must match sign() in frontend/middleware.ts."""
    mac = hmac.new(secret.encode(), f"{COOKIE}.{exp}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


def valid_session(cookie_header: str | None, secret: str | None, now: float | None = None) -> bool:
    if not secret or not cookie_header:
        return False
    try:
        morsel = SimpleCookie(cookie_header).get(COOKIE)
    except CookieError:
        return False
    exp, _, sig = (morsel.value if morsel else "").partition(".")
    if not exp.isdigit() or int(exp) < (now or time.time()):
        return False
    return secrets.compare_digest(sig.encode(), session_sig(int(exp), secret).encode())


@app.middleware("http")
async def gate(request: Request, call_next):
    secret = os.getenv("ADMIN_PASSWORD")
    if not (
        authorized(request.headers.get("authorization"), secret)
        or valid_session(request.headers.get("cookie"), secret)
    ):
        # no WWW-Authenticate: the browser must not pop its own password box; the site redirects to sign-in
        return JSONResponse(
            {"detail": "Sign in required."}, status_code=401, headers={"Cache-Control": "no-store"}
        )
    return await call_next(request)


# Trade Lab first: the Daily desk's /admin/desk/{day} would otherwise catch /admin/desk/trade
app.include_router(trade.router)
app.include_router(admin_desk.router)


@app.on_event("startup")
def _recover_trade_lab() -> None:
    """A deploy restarts the machine: steps that were running can't finish, so mark them for Retry."""
    from castelino.agents.trade import runner

    runner.recover_interrupted()
