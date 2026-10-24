"""Benchmark recorder: every AI call and every admin action, kept for testing new models later.

Two append-only logs under `data/benchmark/` (or $ARC_BENCHMARK_DIR), one gzip JSONL file a day:

- `calls/<day>.jsonl.gz`: one line per model call, with everything a replay needs (agent, model,
  the full input as sent, the output, time taken, tokens, error). Ids let ratings point at a call.
- `actions/<day>.jsonl.gz`: what the admin did (chat, rerun, rebuild, push_draft, x_post, rate).
  A rating is an action: {"action": "rate", "call_id", "rating": "up"|"down", "better"}.
- `x/<day>.jsonl.gz`: one line per billed X API call, {"at", "kind", "n"} (record_x); costs.py
  prices it for admin → Costs.

Recording never breaks a run: a failed write is only logged. Admin-only data: it lives on the
data volume and is never exported to the public site. Appending to a .gz file adds a gzip
member, which `gzip.open` reads back as one stream.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)
_lock = threading.Lock()


def root() -> Path:
    if env := os.environ.get("ARC_BENCHMARK_DIR"):
        return Path(env)
    from castelino.config import get_settings

    return get_settings().root / "data" / "benchmark"


def _append(kind: str, row: dict) -> None:
    try:
        d = root() / kind
        d.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        with (
            _lock,
            gzip.open(d / f"{datetime.now():%Y-%m-%d}.jsonl.gz", "at", encoding="utf-8") as f,
        ):
            f.write(line)
    except Exception:  # noqa: BLE001 — the benchmark must never break a run
        log.warning("benchmark write failed", exc_info=True)


def record_x(kind: str, n: int = 1) -> None:
    """Log one billed X API call: "post", "post_link" (a post carrying a URL) or "read" (n = the
    posts it returned). costs.X_FEES prices them."""
    _append("x", {"at": datetime.now().isoformat(timespec="seconds"), "kind": kind, "n": n})


def record_call(
    agent: str,
    model: str,
    input: dict,
    output=None,
    *,
    started: float,
    tokens: tuple[int | None, int | None] = (None, None),
    error: str | None = None,
) -> str:
    """Log one model call; returns its id. `started` is a time.monotonic() reading."""
    cid = uuid.uuid4().hex[:16]
    if hasattr(output, "model_dump"):
        output = output.model_dump()
    _append(
        "calls",
        {
            "id": cid,
            "at": datetime.now().isoformat(timespec="seconds"),
            "agent": agent,
            "model": model,
            "input": input,
            "output": output,
            "ms": int((time.monotonic() - started) * 1000),
            "tokens_in": tokens[0],
            "tokens_out": tokens[1],
            "error": error,
        },
    )
    return cid


def record_action(action: str, **fields) -> None:
    _append(
        "actions", {"at": datetime.now().isoformat(timespec="seconds"), "action": action, **fields}
    )


def response_output(resp) -> dict:
    """What an OpenAI Responses API reply said: its text and any tool calls it asked for."""
    calls = [
        {"name": o.name, "arguments": o.arguments}
        for o in getattr(resp, "output", None) or []
        if getattr(o, "type", "") == "function_call"
    ]
    return {"text": getattr(resp, "output_text", "") or "", "function_calls": calls}


def usage_of(resp) -> tuple[int | None, int | None]:
    u = getattr(resp, "usage", None)
    if u is None:
        return None, None
    tin = getattr(u, "input_tokens", None) or getattr(u, "prompt_tokens", None)
    tout = getattr(u, "output_tokens", None) or getattr(u, "completion_tokens", None)
    return tin, tout


def read(kind: str, day: str) -> list[dict]:
    """All rows of one day's log (for the replay script and tests)."""
    p = root() / kind / f"{day}.jsonl.gz"
    if not p.exists():
        return []
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
