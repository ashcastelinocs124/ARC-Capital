"""LLM-generates a PersonaCard from a sample of corpus chunks."""
from __future__ import annotations

from castelino.agents.base import LLMClient
from castelino.agents.personas.corpus import CorpusChunk
from castelino.agents.personas.models import PersonaCard


SYSTEM = """\
You analyze a sample of a public figure's writings to produce a structured
profile card. Extract their stable beliefs, decision-making heuristics,
signature phrases, and famous historical calls. Be specific and concrete;
avoid platitudes. If a field can't be supported by the sample, leave it
empty rather than inventing.
"""


USER = """\
Profile this figure:
- persona_id: {persona_id}
- full_name: {full_name}
- role: {role}

Sample of their writings ({n_chunks} chunks):
{joined}

Return a PersonaCard JSON.
"""


def generate_profile_card(
    *,
    client: LLMClient,
    persona_id: str,
    full_name: str,
    role: str,
    sample_chunks: list[CorpusChunk],
    model: str = "gpt-4o",
) -> PersonaCard:
    joined = "\n\n---\n\n".join(c.text for c in sample_chunks)
    return client.parse(
        model=model,
        system=SYSTEM,
        user=USER.format(
            persona_id=persona_id, full_name=full_name, role=role,
            n_chunks=len(sample_chunks), joined=joined,
        ),
        schema=PersonaCard,
        max_tokens=1500,
    )
