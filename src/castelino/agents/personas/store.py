"""Per-persona Chroma collection + embedder.

In-memory mode for tests; persistent mode for production. Embeddings via
OpenAI text-embedding-3-small (configurable via PersonaCfg). Test fixtures
monkeypatch _embed to avoid network calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from castelino.agents.personas.corpus import CorpusChunk
from castelino.config import get_settings


@dataclass(frozen=True)
class QueryHit:
    id: str
    text: str
    metadata: dict
    score: float


class PersonaStore:
    """Thin wrapper around a Chroma collection scoped to one persona_id."""

    def __init__(self, *, persona_id: str, in_memory: bool = False):
        import chromadb

        self.persona_id = persona_id
        cfg = get_settings()
        if in_memory:
            self._client = chromadb.EphemeralClient()
        else:
            path = Path(cfg.personas.chroma_path) / persona_id
            path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(persona_id)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Override in tests via monkeypatch."""
        from openai import OpenAI

        client = OpenAI()
        cfg = get_settings()
        resp = client.embeddings.create(
            model=cfg.personas.embedding_model, input=texts,
        )
        return [d.embedding for d in resp.data]

    def add_chunks(self, chunks: list[CorpusChunk]) -> None:
        if not chunks:
            return
        embeddings = self._embed([c.text for c in chunks])
        self._collection.add(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            metadatas=[c.metadata for c in chunks],
            documents=[c.text for c in chunks],
        )

    def query(self, text: str, *, top_k: int = 6) -> list[QueryHit]:
        if self._collection.count() == 0:
            return []
        emb = self._embed([text])
        result = self._collection.query(
            query_embeddings=emb, n_results=min(top_k, self._collection.count()),
        )
        hits = []
        for i in range(len(result["ids"][0])):
            hits.append(
                QueryHit(
                    id=result["ids"][0][i],
                    text=result["documents"][0][i],
                    metadata=result["metadatas"][0][i] or {},
                    score=1.0 / (1.0 + result["distances"][0][i]),
                )
            )
        return hits
