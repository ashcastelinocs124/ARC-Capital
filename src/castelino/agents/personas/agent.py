"""Per-turn persona chat: retrieval + system prompt + LLM call."""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from castelino.agents.base import LLMClient
from castelino.agents.personas.models import (
    Citation, PersonaCard, PersonaConversation, PersonaMessage,
)
from castelino.agents.personas.store import PersonaStore
from castelino.config import get_settings


class PersonaResponse(BaseModel):
    """Structured LLM response: response text + which sources it actually used."""
    text: str
    cited_sources: list[str] = Field(default_factory=list)


SYSTEM_TEMPLATE = """\
You are responding AS {full_name} ({role}).

Belief summary: {belief_summary}
Decision framework: {framework}
Voice notes: {voice}

You will be given the human's question and a set of passages from your own
prior writings. When relevant, ground your reply in those passages and
include their source identifiers in `cited_sources`. NEVER cite a source
that wasn't in the passages provided. If a question is outside your scope
or expertise, say so honestly rather than improvising.

Stay in character. Be direct and specific.
"""


PASSAGES_HEADER = "\nRelevant passages from your own writings:\n"


class PersonaAgent:
    def __init__(
        self,
        *,
        persona_id: str,
        client: LLMClient,
        data_root: Path | None = None,
        in_memory_store: bool = False,
    ):
        self.persona_id = persona_id
        self.client = client
        cfg = get_settings()
        self.cfg = cfg
        self.data_root = data_root or Path("data") / "personas"
        self.store = PersonaStore(persona_id=persona_id, in_memory=in_memory_store)
        self.card = self._load_card()

    def _load_card(self) -> PersonaCard:
        p = self.data_root / "agents" / self.persona_id / "profile.yaml"
        raw = yaml.safe_load(p.read_text())
        return PersonaCard.model_validate(raw)

    def _system_prompt(self, hits) -> str:
        passages = "\n\n---\n".join(
            f"[{h.metadata.get('source','?')}] {h.text}" for h in hits
        )
        return SYSTEM_TEMPLATE.format(
            full_name=self.card.full_name, role=self.card.role,
            belief_summary=self.card.belief_summary,
            framework="; ".join(self.card.decision_framework),
            voice=self.card.voice_notes,
        ) + PASSAGES_HEADER + passages

    def chat(
        self,
        *,
        conversation: PersonaConversation,
        user_text: str,
        approval_payload: dict,
    ) -> PersonaMessage:
        retrieval_q = (
            user_text + "\n[context] " + str(approval_payload.get("thesis", ""))
        )
        hits = self.store.query(retrieval_q, top_k=self.cfg.personas.retrieval_top_k)

        user_msg = PersonaMessage(role="user", text=user_text,
                                  timestamp=datetime.now(UTC))
        conversation.messages.append(user_msg)

        history_lines = "\n".join(
            f"{m.role.upper()}: {m.text}" for m in conversation.messages
        )
        user_prompt = f"{history_lines}\n\nRespond as {self.card.full_name}."

        resp: PersonaResponse = self.client.parse(
            model=self.cfg.personas.chat_model,
            system=self._system_prompt(hits),
            user=user_prompt,
            schema=PersonaResponse,
            max_tokens=600,
        )

        cited_set = set(resp.cited_sources)
        citations = []
        for h in hits:
            src = h.metadata.get("source", "")
            if src in cited_set:
                citations.append(Citation(source=src, snippet=h.text[:200],
                                          score=h.score))

        assistant_msg = PersonaMessage(
            role="assistant", text=resp.text,
            timestamp=datetime.now(UTC),
            citations=citations,
        )
        conversation.messages.append(assistant_msg)
        return assistant_msg
