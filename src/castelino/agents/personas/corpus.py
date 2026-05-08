"""Corpus document model + token-aware chunker.

Token counts are approximate (whitespace-split count). Good enough for
chunk-size budgets — the embedder sees the actual text.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CorpusDoc:
    source: str
    date: datetime
    title: str
    text: str
    url: str


@dataclass(frozen=True)
class CorpusChunk:
    id: str
    text: str
    metadata: dict


def _tokens(text: str) -> list[str]:
    return text.split()


def chunk_docs(
    docs: list[CorpusDoc],
    *,
    max_tokens: int,
    overlap: int,
) -> list[CorpusChunk]:
    out: list[CorpusChunk] = []
    for d in docs:
        tokens = _tokens(d.text)
        if not tokens:
            continue
        step = max(1, max_tokens - overlap)
        for i in range(0, len(tokens), step):
            window = tokens[i : i + max_tokens]
            if not window:
                continue
            chunk_text = " ".join(window)
            cid_seed = f"{d.source}|{d.url}|{i}|{chunk_text[:40]}"
            cid = hashlib.sha1(cid_seed.encode()).hexdigest()[:16]
            out.append(CorpusChunk(
                id=cid,
                text=chunk_text,
                metadata={
                    "source": d.source,
                    "title": d.title,
                    "date": d.date.isoformat(),
                    "url": d.url,
                    "chunk_index": i // step,
                },
            ))
    return out
