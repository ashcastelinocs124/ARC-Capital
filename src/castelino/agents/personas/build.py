"""Full persona build pipeline: scrape -> chunk -> embed -> card."""
from __future__ import annotations

import json
import random
from datetime import datetime, UTC
from pathlib import Path

import yaml

from castelino.agents.base import LLMClient
from castelino.agents.personas.card_builder import generate_profile_card
from castelino.agents.personas.corpus import CorpusChunk, chunk_docs
from castelino.agents.personas.models import PersonaCard
from castelino.agents.personas.store import PersonaStore
from castelino.config import get_settings


SCRAPERS_REGISTRY: dict[str, type] = {}


def register_scraper(persona_id: str, scraper_cls: type) -> None:
    SCRAPERS_REGISTRY[persona_id] = scraper_cls


def _seed_registry_once() -> None:
    if SCRAPERS_REGISTRY:
        return
    from castelino.agents.personas.scrapers.buffett import BuffettScraper
    register_scraper("buffett", BuffettScraper)


def _stratified_sample(chunks: list[CorpusChunk], n: int) -> list[CorpusChunk]:
    if len(chunks) <= n:
        return chunks
    rng = random.Random(42)
    return rng.sample(chunks, n)


def _save_card(card: PersonaCard, agents_dir: Path) -> Path:
    out = agents_dir / card.persona_id / "profile.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(json.loads(card.model_dump_json()),
                                  sort_keys=False))
    return out


def _save_manifest(persona_id: str, agents_dir: Path,
                   sources: list[str]) -> None:
    out = agents_dir / persona_id / "corpus_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "persona_id": persona_id,
        "fetched_at": datetime.now(UTC).isoformat(),
        "sources": sources,
    }, indent=2))


async def build_persona(
    *,
    persona_id: str,
    full_name: str,
    role: str,
    client: LLMClient,
    data_root: Path | None = None,
    in_memory_store: bool = False,
) -> PersonaCard:
    _seed_registry_once()
    cfg = get_settings()
    if data_root is None:
        data_root = Path("data") / "personas"
    agents_dir = data_root / "agents"

    scraper_cls = SCRAPERS_REGISTRY.get(persona_id)
    if scraper_cls is None:
        raise KeyError(f"No scraper registered for {persona_id}")
    scraper = scraper_cls()

    docs = await scraper.fetch()
    chunks = chunk_docs(
        docs,
        max_tokens=cfg.personas.chunk_max_tokens,
        overlap=cfg.personas.chunk_overlap_tokens,
    )

    store = PersonaStore(persona_id=persona_id, in_memory=in_memory_store)
    store.add_chunks(chunks)

    sample = _stratified_sample(chunks, n=30)
    card = generate_profile_card(
        client=client, persona_id=persona_id,
        full_name=full_name, role=role,
        sample_chunks=sample,
    )

    _save_card(card, agents_dir)
    _save_manifest(persona_id, agents_dir, sources=[d.source for d in docs])
    return card
