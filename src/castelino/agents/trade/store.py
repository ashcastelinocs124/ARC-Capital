"""One folder per idea: data/trades/<id>/idea.json (+ charts/, substack.json). Gitignored, never exported.

`edit()` is the only way steps and the API change a saved idea: it reloads under a per-idea lock and saves on
exit, so a talk message and a background step writing at once never lose each other's change."""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from castelino.agents.trade.models import TradeIdea
from castelino.agents.update.fsio import atomic_write_text
from castelino.config import get_settings

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def root() -> Path:
    if env := os.environ.get("ARC_TRADE_DIR", "").strip():
        return Path(env)
    cfg = get_settings()
    return cfg.root / cfg.trade_lab.data_dir


def idea_dir(idea_id: str) -> Path:
    return root() / idea_id


def charts_dir(idea_id: str) -> Path:
    return idea_dir(idea_id) / "charts"


def _lock(idea_id: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(idea_id, threading.Lock())


def save(idea: TradeIdea) -> None:
    idea.updated_at = now()
    atomic_write_text(idea_dir(idea.id) / "idea.json", idea.model_dump_json(indent=1))


def load(idea_id: str) -> TradeIdea:
    p = idea_dir(idea_id) / "idea.json"
    if "/" in idea_id or ".." in idea_id or not p.exists():
        raise KeyError(idea_id)
    return TradeIdea.model_validate_json(p.read_text())


def create(text: str) -> TradeIdea:
    # microseconds: two ideas made in the same second still list in order
    created = datetime.now().isoformat(timespec="microseconds")
    idea = TradeIdea(
        id=uuid.uuid4().hex[:10], idea=text.strip(), created_at=created, updated_at=now()
    )
    charts_dir(idea.id).mkdir(parents=True, exist_ok=True)
    save(idea)
    return idea


@contextmanager
def edit(idea_id: str):
    with _lock(idea_id):
        idea = load(idea_id)
        yield idea
        save(idea)


def all() -> list[TradeIdea]:  # noqa: A001 - store.all() reads as English at call sites
    out: list[TradeIdea] = []
    if not root().exists():
        return out
    for p in root().glob("*/idea.json"):
        try:
            out.append(TradeIdea.model_validate_json(p.read_text()))
        except ValueError:
            continue
    return sorted(out, key=lambda i: i.created_at + i.id, reverse=True)


def hide(idea_id: str) -> None:
    with _lock(idea_id):
        load(idea_id)  # KeyError if unknown
        dest = root() / "hidden" / idea_id
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(idea_dir(idea_id)), dest)
