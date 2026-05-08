import asyncio
from datetime import datetime, UTC

import pytest

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.build import build_persona
from castelino.agents.personas.corpus import CorpusDoc
from castelino.agents.personas.models import PersonaCard


def test_build_persona_writes_card_yaml(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    # Buffett scraper kept as a reference impl but no longer in the default
    # registry (he's a value investor, not macro). Register him explicitly
    # for this test to exercise the build pipeline end-to-end.
    from castelino.agents.personas.build import register_scraper
    from castelino.agents.personas.scrapers.buffett import BuffettScraper
    register_scraper("buffett", BuffettScraper)

    async def _fake_fetch(self):
        return [CorpusDoc(
            source="b1.pdf", date=datetime(2008, 12, 31, tzinfo=UTC),
            title="t",
            text="quality companies forever margin safety " * 50,
            url="https://x/b1.pdf",
        )]
    monkeypatch.setattr(BuffettScraper, "fetch", _fake_fetch)

    from castelino.agents.personas.store import PersonaStore
    monkeypatch.setattr(
        PersonaStore, "_embed",
        lambda self, texts: [[float(ord(t[0])), 0.0, 0.0] for t in texts],
    )

    fake = FakeLLMClient()
    fake.register("PersonaCard", lambda system, user: PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="1965-present",
        belief_summary="quality forever",
        decision_framework=["margin of safety"],
        signature_phrases=[], famous_calls=[], voice_notes="folksy",
    ))

    asyncio.run(build_persona(
        persona_id="buffett",
        full_name="Warren Buffett",
        role="Value investor",
        client=fake,
        data_root=tmp_path,
        in_memory_store=True,
    ))

    profile_path = tmp_path / "agents" / "buffett" / "profile.yaml"
    assert profile_path.exists()
    text = profile_path.read_text()
    assert "Warren Buffett" in text

    manifest_path = tmp_path / "agents" / "buffett" / "corpus_manifest.json"
    assert manifest_path.exists()


def test_build_persona_unknown_id_raises():
    # Default registry is empty (macro-only roster, scrapers register
    # themselves as added). Any persona_id raises KeyError until wired.
    from castelino.agents.personas.build import SCRAPERS_REGISTRY
    SCRAPERS_REGISTRY.clear()
    fake = FakeLLMClient()
    with pytest.raises(KeyError):
        asyncio.run(build_persona(
            persona_id="not_real", full_name="X", role="Y",
            client=fake, in_memory_store=True,
        ))
