"""Panel discussion: parallel persona fan-out + synthesis pass."""
from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from pathlib import Path

from castelino.agents.base import LLMClient
from castelino.agents.personas.agent import PersonaAgent
from castelino.agents.personas.models import (
    PanelDiscussion, PanelResponse, PanelSynthesis, PersonaConversation,
)
from castelino.config import get_settings
from castelino.orchestrator.approval import ApprovalQueue


SYNTHESIS_SYSTEM = """\
You are a meeting facilitator. You will receive answers from N panelists,
each labelled by name. Identify points of CONSENSUS, points of
DISAGREEMENT (with axis + each panelist's stance), the SINGLE STRONGEST
OBJECTION, and concrete RECOMMENDED MODIFICATIONS the user should
consider. Be specific; avoid platitudes.
"""


class PanelOrchestrator:
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

    def _agent(self, persona_id: str) -> PersonaAgent:
        return PersonaAgent(
            persona_id=persona_id, client=self.client,
            data_root=self.data_root, in_memory_store=self.in_memory_store,
        )

    async def _ask_one(self, persona_id: str, item, question: str) -> PanelResponse:
        agent = self._agent(persona_id)
        throwaway = PersonaConversation(
            entry_id=item.entry_id, persona_id=persona_id,
            started_at=datetime.now(UTC), messages=[],
        )
        msg = agent.chat(conversation=throwaway,
                         user_text=question,
                         approval_payload=item.payload)
        return PanelResponse(persona_id=persona_id,
                             text=msg.text, citations=msg.citations)

    async def run(
        self, *,
        entry_id: str,
        personas: list[str],
        question: str,
    ) -> PanelDiscussion:
        cfg = get_settings()
        item = self.queue.get(entry_id)

        responses = await asyncio.gather(*[
            self._ask_one(p, item, question) for p in personas
        ])

        joined = "\n\n".join(
            f"{r.persona_id.upper()}:\n{r.text}" for r in responses
        )
        synthesis = self.client.parse(
            model=cfg.personas.synthesis_model,
            system=SYNTHESIS_SYSTEM,
            user=f"Question: {question}\n\nPanel responses:\n{joined}",
            schema=PanelSynthesis,
            max_tokens=1500,
        )

        panel = PanelDiscussion(
            entry_id=entry_id, question=question,
            responses=list(responses), synthesis=synthesis,
            created_at=datetime.now(UTC),
        )
        item.panel_discussions.append(panel)
        self.queue._items[entry_id] = item
        self.queue._save()
        return panel
