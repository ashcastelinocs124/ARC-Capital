"""Standalone persona chat — free-form, not tied to an approval.

Persists one rolling thread per persona at
data/personas/conversations/<persona_id>.json. 30-day sliding window
for LLM context (older messages stay on disk + UI but don't pay tokens).
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from pathlib import Path

from castelino.agents.base import LLMClient
from castelino.agents.personas.agent import PersonaAgent
from castelino.agents.personas.models import (
    PersonaConversation, PersonaMessage, PersonaStandaloneThread,
)


_LLM_WINDOW_DAYS = 30


class PersonaStandaloneService:
    def __init__(
        self,
        *,
        client: LLMClient,
        data_root: Path | None = None,
        in_memory_store: bool = False,
    ):
        self.client = client
        self.data_root = data_root or Path("data") / "personas"
        self.in_memory_store = in_memory_store
        self._agents: dict[str, PersonaAgent] = {}

    def _agent(self, persona_id: str) -> PersonaAgent:
        if persona_id not in self._agents:
            self._agents[persona_id] = PersonaAgent(
                persona_id=persona_id, client=self.client,
                data_root=self.data_root, in_memory_store=self.in_memory_store,
            )
        return self._agents[persona_id]

    def _thread_path(self, persona_id: str) -> Path:
        return self.data_root / "conversations" / f"{persona_id}.json"

    def load_thread(self, *, persona_id: str) -> PersonaStandaloneThread:
        path = self._thread_path(persona_id)
        if not path.exists():
            now = datetime.now(UTC)
            return PersonaStandaloneThread(
                persona_id=persona_id, started_at=now, last_active_at=now,
            )
        try:
            return PersonaStandaloneThread.model_validate_json(path.read_text())
        except Exception:
            path.rename(path.with_suffix(".json.bak"))
            now = datetime.now(UTC)
            return PersonaStandaloneThread(
                persona_id=persona_id, started_at=now, last_active_at=now,
            )

    def _save_thread(self, thread: PersonaStandaloneThread) -> None:
        path = self._thread_path(thread.persona_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(thread.model_dump_json(indent=2))

    def send(self, *, persona_id: str, user_text: str) -> PersonaMessage:
        thread = self.load_thread(persona_id=persona_id)

        cutoff = datetime.now(UTC) - timedelta(days=_LLM_WINDOW_DAYS)
        windowed = [m for m in thread.messages if m.timestamp >= cutoff]

        adapter = PersonaConversation(
            entry_id="standalone",
            persona_id=persona_id,
            started_at=thread.started_at,
            messages=list(windowed),
        )
        msg = self._agent(persona_id).chat(
            conversation=adapter,
            user_text=user_text,
            approval_payload={},
        )

        # Append the new (user, assistant) pair to the FULL on-disk thread.
        thread.messages.extend(adapter.messages[-2:])
        thread.last_active_at = datetime.now(UTC)
        self._save_thread(thread)
        return msg
