import asyncio
import json
from datetime import datetime, UTC

import pytest
import yaml

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.models import (
    Disagreement, PanelSynthesis, PersonaCard,
)
from castelino.orchestrator.approval import ApprovalQueue, GateType


@pytest.fixture
def queue_two_personas(tmp_path):
    pytest.importorskip("chromadb")
    q = ApprovalQueue(state_dir=tmp_path)
    q.submit(gate=GateType.POST_HYPOTHESIS,
             payload={"thesis": "long XLE"}, entry_id="H-x")
    for pid, name in [("buffett", "Warren Buffett"),
                      ("dalio", "Ray Dalio")]:
        card = PersonaCard(
            persona_id=pid, full_name=name, role="r", tenure="t",
            belief_summary="b", decision_framework=[], signature_phrases=[],
            famous_calls=[], voice_notes="v",
        )
        p = tmp_path / "agents" / pid / "profile.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))
    return q, tmp_path


def test_panel_runs_parallel_then_synthesizes(queue_two_personas, monkeypatch):
    queue, data_root = queue_two_personas
    from castelino.agents.personas.agent import PersonaResponse
    from castelino.agents.personas.panel import PanelOrchestrator

    fake = FakeLLMClient()
    n_persona_calls = {"n": 0}

    def _persona_handler(system, user):
        n_persona_calls["n"] += 1
        return PersonaResponse(text=f"persona-resp-{n_persona_calls['n']}",
                               cited_sources=[])

    fake.register("PersonaResponse", _persona_handler)
    fake.register(
        "PanelSynthesis",
        lambda s, u: PanelSynthesis(
            consensus=["both like the direction"],
            disagreements=[Disagreement(axis="size",
                                        positions={"buffett": "small",
                                                   "dalio": "moderate"})],
            strongest_objection="position is concentrated",
            recommended_modifications=["halve size"],
        ),
    )

    monkeypatch.setattr("castelino.agents.personas.store.PersonaStore._embed",
                        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts])

    orch = PanelOrchestrator(queue=queue, client=fake,
                             data_root=data_root, in_memory_store=True)
    panel = asyncio.run(orch.run(
        entry_id="H-x",
        personas=["buffett", "dalio"],
        question="Is the thesis sound?",
    ))

    assert len(panel.responses) == 2
    assert panel.synthesis.strongest_objection.startswith("position")
    assert n_persona_calls["n"] == 2

    item = queue.get("H-x")
    assert len(item.panel_discussions) == 1
