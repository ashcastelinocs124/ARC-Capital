"""High-level chat service used by dashboard endpoints."""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from castelino.agents.base import LLMClient
from castelino.agents.personas.agent import PersonaAgent
from castelino.agents.personas.models import PersonaConversation, PersonaMessage
from castelino.orchestrator.approval import ApprovalQueue


class PersonaChatService:
    def __init__(
        self,
        *,
        queue: ApprovalQueue,
        client: LLMClient,
        data_root: Path | None = None,
        in_memory_store: bool = False,
    ):
        self.queue = queue
        self.client = client
        self.data_root = data_root
        self.in_memory_store = in_memory_store
        self._agents: dict[str, PersonaAgent] = {}

    def _agent(self, persona_id: str) -> PersonaAgent:
        if persona_id not in self._agents:
            self._agents[persona_id] = PersonaAgent(
                persona_id=persona_id, client=self.client,
                data_root=self.data_root, in_memory_store=self.in_memory_store,
            )
        return self._agents[persona_id]

    def _find_or_create_conv(self, item, persona_id: str) -> PersonaConversation:
        for c in item.conversations:
            if c.persona_id == persona_id:
                return c
        conv = PersonaConversation(
            entry_id=item.entry_id, persona_id=persona_id,
            started_at=datetime.now(UTC), messages=[],
        )
        item.conversations.append(conv)
        return conv

    def send(self, *, entry_id: str, persona_id: str, user_text: str) -> PersonaMessage:
        item = self.queue.get(entry_id)
        conv = self._find_or_create_conv(item, persona_id)
        msg = self._agent(persona_id).chat(
            conversation=conv,
            user_text=user_text,
            approval_payload=item.payload,
        )
        self.queue._items[entry_id] = item
        self.queue._save()
        return msg

    def list_conversations(self, *, entry_id: str) -> list[PersonaConversation]:
        return self.queue.get(entry_id).conversations
