from __future__ import annotations

import logging
import os
from pathlib import Path

from castelino.agents.research.deep.models import ResearchSession
from castelino.config import get_settings

log = logging.getLogger(__name__)


class ResearchStore:
    """Atomic JSON store for research sessions (one file per session)."""

    def __init__(self, root: Path | None = None):
        if root is None:
            cfg = get_settings()
            root = cfg.root / cfg.deep_research.reports_dir
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def save(self, session: ResearchSession) -> None:
        path = self._path(session.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(session.model_dump_json(indent=2))
        os.replace(tmp, path)  # atomic — avoids partial-write corruption

    def load(self, session_id: str) -> ResearchSession | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            return ResearchSession.model_validate_json(path.read_text())
        except Exception as e:  # noqa: BLE001
            log.warning("research session %s corrupt: %s", session_id, e)
            return None

    def list(self) -> list[ResearchSession]:
        out = []
        for p in sorted(self.root.glob("*.json")):
            try:
                out.append(ResearchSession.model_validate_json(p.read_text()))
            except Exception:  # noqa: BLE001
                continue
        return out
