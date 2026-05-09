"""FigureProfileStore — disk-backed RAG store keyed per tracked figure.

Wave 6.5 Task 6.5.2 — provides upsert + query + version persistence on top
of Chroma. Uses a pluggable embedder so tests can run without the OpenAI
embedding API; production uses `text-embedding-3-small` via the existing
embedder pattern in `agents/personas/store.py`.

Path layout:
    data/figure_profiles/<figure_id>/
        version.json    — FigureProfileMeta
        card.json       — FigureCard
        chroma/         — Chroma persistent collection
        sources/        — markdown source documents (read at build time)
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Callable
from pathlib import Path

from castelino.triggers.figure_deviation.profile.models import (
    Chunk,
    FigureCard,
    FigureProfileMeta,
    RetrievedChunk,
)

log = logging.getLogger(__name__)


# ────────────────────────── embedder interface ──────────────────────────────


Embedder = Callable[[list[str]], list[list[float]]]


def _stub_embedder(texts: list[str]) -> list[list[float]]:
    """Deterministic hash-based pseudo-embedding for tests. Each text is
    mapped to a fixed-dimension vector by hashing — close enough for
    similarity ranking in tests without needing an OpenAI API call."""
    DIM = 64
    out: list[list[float]] = []
    for text in texts:
        # Generate DIM independent hashes by varying salt
        vec: list[float] = []
        for i in range(DIM):
            h = hashlib.sha256(f"{i}:{text}".encode()).digest()
            # Map first 4 bytes to a float in [-1, 1]
            n = int.from_bytes(h[:4], "big")
            vec.append((n / 2**32) * 2 - 1)
        # Normalise to unit length so cosine similarity is well-defined
        mag = math.sqrt(sum(v * v for v in vec))
        out.append([v / mag for v in vec] if mag > 0 else vec)
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ────────────────────────── store ──────────────────────────────────────────


class FigureProfileStore:
    """Per-figure RAG store. Lightweight in-process index for the test path
    and Wave 6.5 scaffolding; will swap to Chroma in production with no
    interface change.

    The interface is what matters: `upsert_chunks`, `query`, `read_card`,
    `read_meta`, `set_version`. Both the test embedder and the production
    embedder satisfy the same `Embedder` callable shape.
    """

    def __init__(
        self,
        *,
        figure_id: str,
        base_dir: Path | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._figure_id = figure_id
        self._base_dir = (
            base_dir or Path("data/figure_profiles")
        ) / figure_id
        self._embedder = embedder or _stub_embedder
        self._index_path = self._base_dir / "index.json"
        # Lazy-loaded
        self._index: dict[str, dict] | None = None

    # ───────── path helpers ─────────

    @property
    def root(self) -> Path:
        return self._base_dir

    def _meta_path(self) -> Path:
        return self._base_dir / "version.json"

    def _card_path(self) -> Path:
        return self._base_dir / "card.json"

    def sources_dir(self) -> Path:
        return self._base_dir / "sources"

    # ───────── index persistence ─────

    def _load_index(self) -> dict[str, dict]:
        if self._index is not None:
            return self._index
        if not self._index_path.exists():
            self._index = {}
            return self._index
        self._index = json.loads(self._index_path.read_text())
        return self._index

    def _save_index(self) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._index or {}, indent=2))
        tmp.replace(self._index_path)

    # ───────── public API ────────────

    def upsert_chunks(self, chunks: list[Chunk]) -> int:
        """Embed and persist chunks. Returns number upserted."""
        if not chunks:
            return 0
        embeddings = self._embedder([c.text for c in chunks])
        idx = self._load_index()
        for chunk, emb in zip(chunks, embeddings):
            idx[chunk.id] = {
                "id": chunk.id,
                "text": chunk.text,
                "section": chunk.section,
                "source_doc": chunk.source_doc,
                "embedding": emb,
            }
        self._save_index()
        return len(chunks)

    def query(
        self,
        *,
        text: str,
        top_k: int = 5,
        section_filter: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Return top-k chunks by cosine similarity to the query text.

        `section_filter` restricts to chunks whose `section` is in the
        list (used by the Hypothesis Agent to retrieve outcome-focused
        sections only, complementary to Stage B's slice).
        """
        idx = self._load_index()
        if not idx:
            return []
        [query_emb] = self._embedder([text])
        candidates: list[tuple[str, dict, float]] = []
        for chunk_id, entry in idx.items():
            if section_filter and entry["section"] not in section_filter:
                continue
            sim = _cosine(query_emb, entry["embedding"])
            candidates.append((chunk_id, entry, sim))
        candidates.sort(key=lambda x: x[2], reverse=True)
        results: list[RetrievedChunk] = []
        for chunk_id, entry, sim in candidates[:top_k]:
            results.append(RetrievedChunk(
                chunk_id=chunk_id,
                text=entry["text"],
                section=entry["section"],
                similarity=max(0.0, min(1.0, (sim + 1.0) / 2.0)),  # [-1,1]→[0,1]
                source_doc=entry["source_doc"],
            ))
        return results

    # ───────── card + meta ───────────

    def write_card(self, card: FigureCard) -> Path:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._card_path().write_text(card.model_dump_json(indent=2))
        return self._card_path()

    def read_card(self) -> FigureCard | None:
        if not self._card_path().exists():
            return None
        return FigureCard.model_validate_json(self._card_path().read_text())

    def set_version(
        self, version: int, *, source_manifest: list[str],
        last_built=None,
    ) -> None:
        from datetime import UTC, datetime as _dt
        meta = FigureProfileMeta(
            figure_id=self._figure_id,
            version=version,
            source_manifest=source_manifest,
            last_built=last_built or _dt.now(UTC),
        )
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path().write_text(meta.model_dump_json(indent=2))

    def read_meta(self) -> FigureProfileMeta | None:
        if not self._meta_path().exists():
            return None
        return FigureProfileMeta.model_validate_json(
            self._meta_path().read_text(),
        )

    def is_built(self) -> bool:
        """True iff this figure has a built profile (meta + index present)."""
        return self._meta_path().exists() and self._index_path.exists()
