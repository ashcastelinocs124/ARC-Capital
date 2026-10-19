"""Research sessions: one JSON file each, data/research/<id>.json (gitignored).

`edit()` is the only way steps and the API change a saved session: it reloads under a per-session lock and
saves on exit, so a background step and an approval never lose each other's change (Trade Lab's store)."""

from __future__ import annotations

import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from castelino.agents.research.deep.models import Clarification, ResearchSession
from castelino.agents.update.fsio import atomic_write_text
from castelino.config import get_settings

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def root() -> Path:
    if env := os.environ.get("ARC_RESEARCH_DIR", "").strip():
        return Path(env)
    cfg = get_settings()
    return cfg.root / cfg.deep_research.data_dir


def _path(sid: str) -> Path:
    return root() / f"{sid}.json"


def _lock(sid: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(sid, threading.Lock())


def save(s: ResearchSession) -> None:
    s.updated_at = now()
    atomic_write_text(_path(s.id), s.model_dump_json(indent=1))


def load(sid: str) -> ResearchSession:
    p = _path(sid)
    if "/" in sid or ".." in sid or not p.exists():
        raise KeyError(sid)
    return ResearchSession.model_validate_json(p.read_text())


def create(topic: str, clar: Clarification, cost: float = 0.0) -> ResearchSession:
    # microseconds: two sessions made in the same second still list in order
    created = datetime.now().isoformat(timespec="microseconds")
    s = ResearchSession(
        id=uuid.uuid4().hex[:10],
        topic=topic.strip(),
        question=clar.question,
        clarifying_questions=clar.questions,
        cost_usd=round(cost, 4),
        created_at=created,
        updated_at=now(),
    )
    save(s)
    return s


@contextmanager
def edit(sid: str):
    with _lock(sid):
        s = load(sid)
        yield s
        save(s)


def all() -> list[ResearchSession]:  # noqa: A001 - store.all() reads as English at call sites
    if not root().exists():
        return []
    out: list[ResearchSession] = []
    for p in root().glob("*.json"):
        try:
            out.append(ResearchSession.model_validate_json(p.read_text()))
        except ValueError:  # the first engine's files and anything half-written
            continue
    return sorted(out, key=lambda s: s.created_at + s.id, reverse=True)
