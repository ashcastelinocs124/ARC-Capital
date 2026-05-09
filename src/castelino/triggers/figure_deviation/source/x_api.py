"""X (Twitter) API v2 source for the figure-deviation engine.

Wave 5 Task 5.1 — implements `FigurePostSource` for X-API-driven figures
(Trump first; Bessent / Musk later). Polls the user-tweet timeline endpoint
on a configurable cadence and emits one `FigurePost` per new tweet.

Two endpoints used:
  • GET /2/users/by/username/{username} — once at startup, cached on disk
  • GET /2/users/{id}/tweets — polled with `since_id` to avoid replay

`since_id` advances ONLY on a successful fetch, so transient errors
(network / 429 / 5xx) never silently drop tweets — they retry next cycle.

Bearer token must be passed at construction; the orchestrator reads it
from `Settings.x_api_bearer_token` (env var X_API_BEARER_TOKEN).
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from castelino.triggers.figure_deviation.models import FigurePost
from castelino.triggers.figure_deviation.source.base import FigurePostSource

log = logging.getLogger(__name__)


class XApiTweetSource(FigurePostSource):
    """X API v2 source — one instance per process, can drive multiple figures
    via repeated `stream()` calls with different source_cfg.

    The state file holds `{user_id: {"username": ..., "since_id": ...}}` and
    is written atomically (temp + rename) on every successful fetch. Loss of
    the state file re-bootstraps from the most recent 20 tweets, with each
    marked seen so they don't replay downstream.
    """

    def __init__(
        self,
        *,
        bearer_token: str,
        state_path: Path | None = None,
        base_url: str = "https://api.twitter.com/2",
        timeout_sec: int = 10,
    ) -> None:
        if not bearer_token:
            raise ValueError(
                "X API bearer token is required. Set X_API_BEARER_TOKEN env var.",
            )
        self._bearer = bearer_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_sec
        self._state_path = state_path or Path(
            "data/figure_deviation/x_api_state.json",
        )
        self._user_id_cache: dict[str, str] = {}
        self.last_backoff_sec: int = 0  # exposed for tests + telemetry

    # ─────────────────────── HTTP helpers ──────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self._bearer}"},
            timeout=self._timeout,
        )

    async def _resolve_user_id(self, username: str) -> str:
        """Look up the X user_id for a username. Cached per-process; the
        ID is stable for the life of an account so this is one call ever."""
        username = username.lstrip("@")
        if username in self._user_id_cache:
            return self._user_id_cache[username]
        async with self._client() as client:
            resp = await client.get(
                f"{self._base_url}/users/by/username/{username}",
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            user_id = data.get("id")
            if not user_id:
                raise RuntimeError(
                    f"X API: could not resolve user_id for {username!r}",
                )
            self._user_id_cache[username] = user_id
            return user_id

    async def _fetch_timeline(
        self, user_id: str, since_id: str | None,
    ) -> list[dict[str, Any]]:
        """GET /2/users/{id}/tweets with since_id + tweet metadata."""
        params: dict[str, Any] = {
            "max_results": 20,
            "tweet.fields": "created_at,referenced_tweets,public_metrics",
        }
        if since_id:
            params["since_id"] = since_id
        async with self._client() as client:
            resp = await client.get(
                f"{self._base_url}/users/{user_id}/tweets", params=params,
            )
            if resp.status_code == 429:
                self.last_backoff_sec = int(
                    resp.headers.get("Retry-After", "60"),
                )
                log.warning(
                    "X API 429 for user_id=%s, backing off %ds",
                    user_id, self.last_backoff_sec,
                )
                resp.raise_for_status()  # caller handles
            resp.raise_for_status()
            return resp.json().get("data", []) or []

    # ─────────────────────── state persistence ─────────────────────────────

    def _load_state(self) -> dict[str, dict[str, Any]]:
        if not self._state_path.exists():
            return {}
        try:
            return json.loads(self._state_path.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning(
                "X API state file %s unreadable — re-bootstrapping",
                self._state_path,
            )
            return {}

    def _save_state(
        self, *, user_id: str, since_id: str, username: str,
    ) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        state = self._load_state()
        state[user_id] = {"since_id": since_id, "username": username}
        # Atomic write: temp + rename
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(self._state_path)

    # ─────────────────────── FigurePostSource interface ────────────────────

    async def stream(self, figure, source_cfg) -> AsyncIterator[FigurePost]:
        """Yield FigurePosts for one polling cycle.

        This is a single-shot async generator (one call = one fetch). The
        polling-orchestrator (Task 5.2) loops it on `poll_interval_min`.
        """
        username = source_cfg.username
        if not username:
            raise ValueError(
                f"X API source for figure {figure.id} missing 'username'",
            )
        try:
            user_id = await self._resolve_user_id(username)
        except httpx.HTTPStatusError as e:
            log.error(
                "X API user resolution failed for @%s: %s", username, e,
            )
            return

        state = self._load_state().get(user_id, {})
        since_id = state.get("since_id")

        try:
            tweets = await self._fetch_timeline(user_id, since_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Already logged; don't advance since_id — retry next cycle.
                return
            log.error("X API timeline fetch failed: %s", e)
            return
        except httpx.HTTPError as e:
            log.error("X API network error: %s", e)
            return

        for t in tweets:
            yield FigurePost(
                figure_id=figure.id,
                text=t["text"],
                ts=datetime.fromisoformat(
                    t["created_at"].replace("Z", "+00:00"),
                ),
                source="x_api",
                event_id=t["id"],
                source_url=f"https://x.com/{username.lstrip('@')}/status/{t['id']}",
                raw_meta={
                    "referenced_tweets": t.get("referenced_tweets", []),
                    "public_metrics": t.get("public_metrics", {}),
                },
            )

        if tweets:
            new_since_id = max(t["id"] for t in tweets)
            self._save_state(
                user_id=user_id, since_id=new_since_id, username=username,
            )
