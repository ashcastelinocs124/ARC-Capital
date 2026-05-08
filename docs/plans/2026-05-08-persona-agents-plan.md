# Persona Agents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let the human consult RAG-backed simulated economists & investors during the existing HITL approval gates, with full chat threads attached to `ApprovalItem` and a multi-persona "panel discussion" mode that surfaces consensus/disagreement.

**Architecture:** Three layers under `src/castelino/agents/personas/`. Layer 1 (offline) per-persona corpus scraper → chunk → embed into a Chroma collection + auto-generates a profile card. Layer 2 (online) `PersonaAgent.chat()` retrieves top-k chunks per turn, builds a card+chunks system prompt, calls the existing `LLMClient`. Layer 3 panel orchestrator does parallel fan-out across N personas then a synthesis pass. Conversations attach to `ApprovalItem.conversations[]`. New dashboard page `/approvals/:id/consult`.

**Tech Stack:** Python 3.11, Pydantic 2.x, Typer, pytest, OpenAI structured output (`chat.completions.parse`), `chromadb` (new dep, local persistent), `pypdf` for PDF scraping (new dep), `youtube-transcript-api` for interview transcripts (new dep), `httpx` + BeautifulSoup (already in repo). Frontend: existing Vite/React app at `frontend/`.

**Reference design:** `docs/plans/2026-05-08-persona-agents-design.md`

**Key learnings to honor (`learnings.md`):**
- Use top-level `chat.completions.parse(response_format=...)` not `.beta.`
- `LLMClient.parse(...)` takes `max_tokens=N` (internally translates to `max_completion_tokens`)
- `FakeLLMClient` uses `register(schema_name, handler)` — NOT `canned=`
- Subagent worktrees branch from `main`. First step in any subagent prompt: `git rebase persona-agent`
- Subagent harness blocks `git commit`. Subagents stage only; parent commits centrally
- Hard rules must be structurally enforced (e.g. retrieval ALWAYS happens before LLM call, panel personas NEVER see each other's drafts)

---

## Task 1: Pydantic conversation + panel models

**Files:**
- Create: `src/castelino/agents/personas/__init__.py` (empty docstring)
- Create: `src/castelino/agents/personas/models.py`
- Test: `tests/test_personas_models.py`

**Step 1: Write the failing tests**

```python
# tests/test_personas_models.py
from datetime import datetime, UTC
from castelino.agents.personas.models import (
    Citation, PersonaMessage, PersonaConversation,
    PanelResponse, Disagreement, PanelSynthesis, PanelDiscussion,
    FamousCall, PersonaCard,
)

def test_citation_roundtrips():
    c = Citation(source="buffett_2008.pdf#p4", snippet="hold forever", score=0.83)
    assert Citation.model_validate_json(c.model_dump_json()) == c

def test_persona_message_with_citations():
    m = PersonaMessage(
        role="assistant", text="Hold quality.",
        timestamp=datetime.now(UTC),
        citations=[Citation(source="x", snippet="y", score=0.9)],
    )
    assert m.role == "assistant"
    assert len(m.citations) == 1

def test_panel_synthesis_schema():
    s = PanelSynthesis(
        consensus=["direction is right"],
        disagreements=[Disagreement(axis="sizing",
                                    positions={"a": "1/3", "b": "2/3"})],
        strongest_objection="Krugman: supply shocks are transitory",
        recommended_modifications=["halve initial size"],
    )
    assert s.disagreements[0].positions["a"] == "1/3"

def test_persona_card_round_trip():
    card = PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="1965-present",
        belief_summary="hold quality companies forever",
        decision_framework=["margin of safety", "circle of competence"],
        signature_phrases=["intrinsic value"],
        famous_calls=[FamousCall(date="2008", description="GS preferred")],
        voice_notes="folksy, anecdotal",
    )
    assert PersonaCard.model_validate_json(card.model_dump_json()) == card
```

**Step 2: Run** `pytest tests/test_personas_models.py -v`. Expect FAIL.

**Step 3: Implement**

```python
# src/castelino/agents/personas/__init__.py
"""Persona-agent system: RAG-backed simulated economists/investors.

The human consults these from the dashboard during HITL approval gates.
Personas do NOT participate in the agent pipeline — they're advisors,
invoked only from the dashboard.
"""
```

```python
# src/castelino/agents/personas/models.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source: str
    snippet: str
    score: float = Field(ge=0.0, le=1.0)


class PersonaMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    timestamp: datetime
    citations: list[Citation] = Field(default_factory=list)


class PersonaConversation(BaseModel):
    entry_id: str
    persona_id: str
    started_at: datetime
    messages: list[PersonaMessage] = Field(default_factory=list)


class PanelResponse(BaseModel):
    persona_id: str
    text: str
    citations: list[Citation] = Field(default_factory=list)


class Disagreement(BaseModel):
    axis: str
    positions: dict[str, str]


class PanelSynthesis(BaseModel):
    consensus: list[str] = Field(default_factory=list)
    disagreements: list[Disagreement] = Field(default_factory=list)
    strongest_objection: str = ""
    recommended_modifications: list[str] = Field(default_factory=list)


class PanelDiscussion(BaseModel):
    entry_id: str
    question: str
    responses: list[PanelResponse]
    synthesis: PanelSynthesis
    created_at: datetime


class FamousCall(BaseModel):
    date: str
    description: str


class PersonaCard(BaseModel):
    persona_id: str
    full_name: str
    role: str
    tenure: str = ""
    belief_summary: str
    decision_framework: list[str] = Field(default_factory=list)
    signature_phrases: list[str] = Field(default_factory=list)
    famous_calls: list[FamousCall] = Field(default_factory=list)
    voice_notes: str = ""
```

**Step 4: Run tests** — expect 4/4 PASS.

**Step 5: Commit**

```
feat(personas): conversation + panel + profile-card Pydantic models
```

---

## Task 2: Extend `ApprovalItem` with `conversations[]` and `panel_discussions[]`

**Files:**
- Modify: `src/castelino/orchestrator/approval.py` (`ApprovalItem` model only)
- Test: `tests/test_personas_approval_extension.py`

**Step 1: Failing test**

```python
# tests/test_personas_approval_extension.py
from datetime import datetime, UTC
from castelino.orchestrator.approval import ApprovalItem, GateType
from castelino.agents.personas.models import (
    PersonaConversation, PersonaMessage, PanelDiscussion, PanelSynthesis,
)

def test_approval_item_has_conversations_default_empty():
    item = ApprovalItem(entry_id="H-1", gate=GateType.POST_HYPOTHESIS)
    assert item.conversations == []
    assert item.panel_discussions == []

def test_approval_item_round_trips_with_conversation():
    conv = PersonaConversation(
        entry_id="H-1", persona_id="buffett",
        started_at=datetime.now(UTC),
        messages=[PersonaMessage(role="user", text="hi", timestamp=datetime.now(UTC))],
    )
    item = ApprovalItem(
        entry_id="H-1", gate=GateType.POST_HYPOTHESIS,
        conversations=[conv],
    )
    raw = item.model_dump_json()
    loaded = ApprovalItem.model_validate_json(raw)
    assert len(loaded.conversations) == 1
    assert loaded.conversations[0].persona_id == "buffett"
```

**Step 2: Run** — expect FAIL.

**Step 3: Modify `ApprovalItem`** in `src/castelino/orchestrator/approval.py`. Add imports:

```python
from castelino.agents.personas.models import PersonaConversation, PanelDiscussion
```

And add to the class:

```python
conversations: list[PersonaConversation] = Field(default_factory=list)
panel_discussions: list[PanelDiscussion] = Field(default_factory=list)
```

**Step 4: Run tests** — expect PASS. Also `pytest tests/test_approval_queue.py` to confirm no regression.

**Step 5: Commit:** `feat(approval): conversations[] + panel_discussions[] on ApprovalItem`

---

## Task 3: `PersonaCfg` config schema

**Files:**
- Modify: `src/castelino/config.py` (add `PersonaCfg`, wire into `Settings`)
- Modify: `config.yaml` (append `personas:` block)
- Test: `tests/test_personas_config.py`

**Step 1: Failing test**

```python
# tests/test_personas_config.py
from castelino.config import get_settings

def test_personas_config_has_defaults():
    s = get_settings()
    assert s.personas.enabled is True
    assert s.personas.chat_model == "gpt-4o-mini"
    assert s.personas.synthesis_model == "gpt-4o"
    assert s.personas.embedding_model == "text-embedding-3-small"
    assert s.personas.retrieval_top_k == 6
    assert "buffett" in s.personas.active_roster
    assert "tudor_jones" in s.personas.active_roster
```

**Step 2: Run** — expect FAIL.

**Step 3: Implement** — add to `src/castelino/config.py` near the existing `*Cfg` classes:

```python
class PersonaCfg(BaseModel):
    enabled: bool = True
    chat_model: str = "gpt-4o-mini"
    synthesis_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    retrieval_top_k: int = 6
    chunk_max_tokens: int = 400
    chunk_overlap_tokens: int = 50
    chroma_path: str = "data/personas/chroma"
    active_roster: list[str] = Field(default_factory=list)
```

Add to `Settings`: `personas: PersonaCfg = PersonaCfg()`.

In `config.yaml`:

```yaml
personas:
  enabled: true
  chat_model: gpt-4o-mini
  synthesis_model: gpt-4o
  embedding_model: text-embedding-3-small
  retrieval_top_k: 6
  chunk_max_tokens: 400
  chunk_overlap_tokens: 50
  chroma_path: data/personas/chroma
  active_roster:
    - krugman
    - el_erian
    - summers
    - buffett
    - druckenmiller
    - dalio
    - tudor_jones
```

**Step 4: Run tests** — expect PASS.

**Step 5: Commit:** `feat(personas): PersonaCfg with v1 roster of 7 personas`

---

## Task 4: `CorpusDoc` model + chunker

**Files:**
- Create: `src/castelino/agents/personas/corpus.py`
- Test: `tests/test_personas_corpus.py`

**Step 1: Failing tests**

```python
# tests/test_personas_corpus.py
from datetime import datetime, UTC
from castelino.agents.personas.corpus import CorpusDoc, chunk_docs


def test_chunk_respects_max_tokens():
    doc = CorpusDoc(
        source="b1.pdf", date=datetime.now(UTC),
        title="t", text="word " * 1000, url="u",
    )
    chunks = chunk_docs([doc], max_tokens=100, overlap=10)
    # ~1000 tokens / (100 - 10) ≈ 11+ chunks
    assert len(chunks) >= 10
    assert all(c.metadata["source"] == "b1.pdf" for c in chunks)


def test_chunk_overlap_creates_continuity():
    doc = CorpusDoc(
        source="x", date=datetime.now(UTC), title="t",
        text=" ".join(str(i) for i in range(200)), url="u",
    )
    chunks = chunk_docs([doc], max_tokens=50, overlap=10)
    # First two chunks must share at least the overlap window
    assert any(tok in chunks[1].text.split()[:10]
               for tok in chunks[0].text.split()[-10:])


def test_chunk_id_is_deterministic():
    doc = CorpusDoc(source="x", date=datetime(2026,1,1,tzinfo=UTC),
                    title="t", text="hello world", url="u")
    a = chunk_docs([doc], max_tokens=50, overlap=5)
    b = chunk_docs([doc], max_tokens=50, overlap=5)
    assert [c.id for c in a] == [c.id for c in b]
```

**Step 2: Run** — expect FAIL.

**Step 3: Implement**

```python
# src/castelino/agents/personas/corpus.py
"""Corpus document model + token-aware chunker.

Token counts are approximate (whitespace-split count). Good enough for
chunk-size budgets — the embedder sees the actual text.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CorpusDoc:
    source: str          # "buffett_letters_2008.pdf"
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
```

**Step 4: Run tests** — expect 3/3 PASS.

**Step 5: Commit:** `feat(personas): CorpusDoc + token-windowed chunker`

---

## Task 5: Chroma wrapper + embedder

**Files:**
- Modify: `pyproject.toml` (add `chromadb>=0.5,<1` to `[project] dependencies`)
- Create: `src/castelino/agents/personas/store.py`
- Test: `tests/test_personas_store.py`

> NOTE: do NOT attempt `pip install` — harness blocks it. Just edit `pyproject.toml`.

**Step 1: Failing tests** (use Chroma's in-memory ephemeral client so no disk):

```python
# tests/test_personas_store.py
import pytest
from datetime import datetime, UTC
from castelino.agents.personas.store import PersonaStore
from castelino.agents.personas.corpus import CorpusChunk


@pytest.fixture
def store():
    return PersonaStore(persona_id="test", in_memory=True)


def test_add_and_query_round_trip(store, monkeypatch):
    # Stub the embedder so tests don't hit the network
    def _fake_embed(texts):
        # Map each unique text to a deterministic vector by hash
        return [[float(ord(t[0])), 0.0, 0.0] for t in texts]
    monkeypatch.setattr(store, "_embed", _fake_embed)

    chunks = [
        CorpusChunk(id="c1", text="apple", metadata={"source": "a"}),
        CorpusChunk(id="c2", text="banana", metadata={"source": "b"}),
        CorpusChunk(id="c3", text="cherry", metadata={"source": "c"}),
    ]
    store.add_chunks(chunks)

    hits = store.query("apple pie", top_k=2)
    assert len(hits) == 2
    # The closest hit should be "apple"
    assert hits[0].text == "apple"
    assert hits[0].metadata["source"] == "a"


def test_collection_isolation_per_persona(monkeypatch):
    a = PersonaStore(persona_id="alpha", in_memory=True)
    b = PersonaStore(persona_id="beta", in_memory=True)
    fake = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]
    monkeypatch.setattr(a, "_embed", fake)
    monkeypatch.setattr(b, "_embed", fake)

    a.add_chunks([CorpusChunk(id="x", text="alpha-doc", metadata={})])
    # b's collection must be empty
    assert b.query("alpha-doc", top_k=1) == []
```

**Step 2: Run** — expect FAIL (module + dep missing).

**Step 3: Add dependency** to `pyproject.toml`:

```
"chromadb>=0.5,<1",
```

**Step 4: Implement** `src/castelino/agents/personas/store.py`:

```python
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
            hits.append(QueryHit(
                id=result["ids"][0][i],
                text=result["documents"][0][i],
                metadata=result["metadatas"][0][i] or {},
                # chroma returns L2 distance; convert to similarity-ish
                score=1.0 / (1.0 + result["distances"][0][i]),
            ))
        return hits
```

**Step 5: Run tests** — expect 2/2 PASS.

**Step 6: Commit:** `feat(personas): PersonaStore Chroma wrapper with stubbable embedder`

---

## Task 6: Profile-card auto-generator

**Files:**
- Create: `src/castelino/agents/personas/card_builder.py`
- Test: `tests/test_personas_card_builder.py`

**Step 1: Failing test**

```python
# tests/test_personas_card_builder.py
from datetime import datetime, UTC
from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.card_builder import generate_profile_card
from castelino.agents.personas.corpus import CorpusChunk
from castelino.agents.personas.models import PersonaCard, FamousCall


def test_generate_profile_card_returns_typed_output():
    canned = PersonaCard(
        persona_id="buffett",
        full_name="Warren Buffett",
        role="Value investor",
        tenure="1965-present",
        belief_summary="hold quality companies forever",
        decision_framework=["margin of safety"],
        signature_phrases=["intrinsic value"],
        famous_calls=[FamousCall(date="2008", description="GS preferred")],
        voice_notes="folksy, anecdotal",
    )
    fake = FakeLLMClient()
    fake.register("PersonaCard", lambda system, user: canned)

    chunks = [CorpusChunk(id="x", text="quality companies", metadata={})]
    card = generate_profile_card(
        client=fake, persona_id="buffett",
        full_name="Warren Buffett", role="Value investor",
        sample_chunks=chunks,
    )
    assert card.persona_id == "buffett"
    assert "intrinsic value" in card.signature_phrases
```

**Step 2: Run** — expect FAIL.

**Step 3: Implement**

```python
# src/castelino/agents/personas/card_builder.py
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
```

**Step 4: Run tests** — expect PASS.

**Step 5: Commit:** `feat(personas): LLM profile-card generator from corpus sample`

---

## Task 7: Scraper base + Buffett implementation

**Files:**
- Modify: `pyproject.toml` (add `pypdf>=4,<6`)
- Create: `src/castelino/agents/personas/scrapers/__init__.py` (empty docstring)
- Create: `src/castelino/agents/personas/scrapers/base.py`
- Create: `src/castelino/agents/personas/scrapers/buffett.py`
- Test: `tests/test_personas_scraper_buffett.py`
- Test fixture: `tests/fixtures/personas/buffett_2008.pdf` (small synthetic PDF)

> Buffett first because his corpus is the smallest cleanest source — annual letters, all on `berkshirehathaway.com`. Validates the architecture before scaling.

**Step 1: Add dep** `pypdf>=4,<6` to `pyproject.toml`.

**Step 2: Failing test** — uses a fixture PDF (you'll create it):

```python
# tests/test_personas_scraper_buffett.py
from pathlib import Path
import pytest
from castelino.agents.personas.scrapers.buffett import BuffettScraper

FIX = Path(__file__).parent / "fixtures" / "personas"


def test_buffett_extracts_pdf_text(monkeypatch):
    pdf_bytes = (FIX / "buffett_2008.pdf").read_bytes()
    scraper = BuffettScraper()

    async def _fake_get(url):
        class _R:
            status_code = 200
            content = pdf_bytes
        return _R()

    monkeypatch.setattr(scraper, "_fetch_pdf", _fake_get)
    monkeypatch.setattr(scraper, "_known_letter_urls",
                        lambda: ["https://www.berkshirehathaway.com/letters/2008ltr.pdf"])
    import asyncio
    docs = asyncio.run(scraper.fetch())
    assert len(docs) >= 1
    d = docs[0]
    assert "berkshire" in d.text.lower() or "shareholders" in d.text.lower()
    assert d.source.endswith(".pdf")
    assert d.date.year == 2008
```

**Step 3: Create fixture** `tests/fixtures/personas/buffett_2008.pdf` — a small valid PDF containing words like "shareholders" or "berkshire" so the test has something to match. You can generate it with `pypdf` itself:

```python
# In a one-off helper if needed:
from pypdf import PdfWriter
w = PdfWriter()
w.add_blank_page(width=72, height=72)
# Use reportlab to add text, or just hand-craft a minimal PDF.
```

For test simplicity, you can also **mock at the parsing layer** — write a `_parse_pdf_bytes` method on `BuffettScraper` and monkeypatch THAT instead of needing a real PDF fixture. That sidesteps the fixture entirely.

**Step 4: Implement base + scraper**

```python
# src/castelino/agents/personas/scrapers/base.py
"""Common scraper contract: async fetch() -> list[CorpusDoc]."""
from __future__ import annotations

from abc import ABC, abstractmethod

from castelino.agents.personas.corpus import CorpusDoc


class PersonaScraper(ABC):
    persona_id: str

    @abstractmethod
    async def fetch(self) -> list[CorpusDoc]:
        ...
```

```python
# src/castelino/agents/personas/scrapers/buffett.py
"""Scrape Berkshire Hathaway annual shareholder letters.

URL pattern: https://www.berkshirehathaway.com/letters/<year>ltr.pdf
Available 1977-present (older years have HTML or different naming).
"""
from __future__ import annotations

from datetime import datetime, UTC

import httpx

from castelino.agents.personas.corpus import CorpusDoc
from castelino.agents.personas.scrapers.base import PersonaScraper


class BuffettScraper(PersonaScraper):
    persona_id = "buffett"
    BASE = "https://www.berkshirehathaway.com/letters/"
    FIRST_YEAR = 1977

    def _known_letter_urls(self) -> list[str]:
        # The naming convention varies by year. Stick to 1977-present for v1.
        # Some years are .pdf, older are .html. Keep it simple: try .pdf only.
        now = datetime.now(UTC).year
        return [f"{self.BASE}{y}ltr.pdf" for y in range(self.FIRST_YEAR, now)]

    async def _fetch_pdf(self, url: str):
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.get(url)

    def _parse_pdf_bytes(self, content: bytes) -> str:
        from io import BytesIO
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(content))
        return "\n".join(p.extract_text() or "" for p in reader.pages)

    def _year_from_url(self, url: str) -> int:
        # ".../letters/2008ltr.pdf" -> 2008
        import re
        m = re.search(r"(\d{4})ltr\.", url)
        return int(m.group(1)) if m else 1900

    async def fetch(self) -> list[CorpusDoc]:
        docs: list[CorpusDoc] = []
        for url in self._known_letter_urls():
            try:
                r = await self._fetch_pdf(url)
                if r.status_code != 200:
                    continue
                text = self._parse_pdf_bytes(r.content)
                if not text.strip():
                    continue
                year = self._year_from_url(url)
                docs.append(CorpusDoc(
                    source=url.rsplit("/", 1)[-1],
                    date=datetime(year, 12, 31, tzinfo=UTC),
                    title=f"Buffett shareholder letter {year}",
                    text=text,
                    url=url,
                ))
            except Exception:
                continue
        return docs
```

**Step 5: Run tests** — expect PASS.

**Step 6: Commit:** `feat(personas): scraper base + Buffett shareholder-letter scraper`

---

## Task 8: `build_persona` orchestrator

**Files:**
- Create: `src/castelino/agents/personas/build.py`
- Test: `tests/test_personas_build.py`

**Step 1: Failing test**

```python
# tests/test_personas_build.py
import asyncio
from datetime import datetime, UTC
from pathlib import Path

import pytest

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.build import build_persona
from castelino.agents.personas.corpus import CorpusDoc
from castelino.agents.personas.models import PersonaCard, FamousCall


def test_build_persona_writes_card_yaml(tmp_path, monkeypatch):
    # Stub scraper so no network
    from castelino.agents.personas.scrapers.buffett import BuffettScraper

    async def _fake_fetch(self):
        return [CorpusDoc(
            source="b1.pdf", date=datetime(2008,12,31,tzinfo=UTC),
            title="t", text="quality companies forever margin safety " * 50,
            url="https://x/b1.pdf",
        )]
    monkeypatch.setattr(BuffettScraper, "fetch", _fake_fetch)

    # Stub embedder
    from castelino.agents.personas.store import PersonaStore
    monkeypatch.setattr(
        PersonaStore, "_embed",
        lambda self, texts: [[float(ord(t[0])), 0.0, 0.0] for t in texts],
    )

    # Stub card-generator LLM
    fake = FakeLLMClient()
    fake.register("PersonaCard", lambda system, user: PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="1965-present",
        belief_summary="quality forever",
        decision_framework=["margin of safety"],
        signature_phrases=[],
        famous_calls=[],
        voice_notes="folksy",
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
```

**Step 2: Run** — expect FAIL.

**Step 3: Implement**

```python
# src/castelino/agents/personas/build.py
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
```

**Step 4: Run tests** — expect PASS.

**Step 5: Commit:** `feat(personas): build_persona orchestrator (scrape→chunk→embed→card)`

---

## Task 9: `castelino persona-build` CLI

**Files:**
- Modify: `src/castelino/orchestrator/cli.py` (add `persona-build` command)
- Test: `tests/test_personas_cli.py`

**Step 1: Failing test**

```python
# tests/test_personas_cli.py
from typer.testing import CliRunner
from castelino.orchestrator.cli import app


def test_persona_build_help_exists():
    r = CliRunner().invoke(app, ["persona-build", "--help"])
    assert r.exit_code == 0
    assert "persona" in r.stdout.lower()
```

**Step 2: Run** — expect FAIL.

**Step 3: Add command** to `src/castelino/orchestrator/cli.py` near other `@app.command` blocks:

```python
@app.command("persona-build")
def persona_build(
    persona_id: str = typer.Option(..., help="Persona id (e.g. buffett)."),
    full_name: str = typer.Option(..., help="Display name."),
    role: str = typer.Option(..., help="Short role label."),
):
    """Scrape primary sources, chunk, embed into Chroma, generate profile card."""
    import asyncio

    from castelino.agents.base import get_llm_client
    from castelino.agents.personas.build import build_persona

    asyncio.run(build_persona(
        persona_id=persona_id, full_name=full_name, role=role,
        client=get_llm_client(),
    ))
    print(f"[green]Persona built:[/green] {persona_id}")
```

**Step 4: Run tests** — expect PASS.

**Step 5: Commit:** `feat(cli): castelino persona-build`

---

## Task 10: `PersonaAgent.chat()` runtime

**Files:**
- Create: `src/castelino/agents/personas/agent.py`
- Test: `tests/test_personas_agent.py`

**Step 1: Failing test**

```python
# tests/test_personas_agent.py
from datetime import datetime, UTC
from pathlib import Path

import pytest
import yaml

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.agent import PersonaAgent
from castelino.agents.personas.corpus import CorpusChunk
from castelino.agents.personas.models import (
    PersonaCard, PersonaConversation, PersonaMessage,
)


@pytest.fixture
def card_on_disk(tmp_path, monkeypatch):
    card = PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="1965-present",
        belief_summary="quality forever",
        decision_framework=["margin of safety"],
        signature_phrases=["intrinsic value"], famous_calls=[],
        voice_notes="folksy",
    )
    p = tmp_path / "agents" / "buffett" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))
    return tmp_path


def test_persona_agent_chat_uses_retrieval_and_llm(card_on_disk, monkeypatch):
    fake = FakeLLMClient()
    fake.register(
        "PersonaResponse",
        lambda system, user: __import__("castelino.agents.personas.agent",
                                       fromlist=["PersonaResponse"])
            .PersonaResponse(text="Hold quality, full stop.",
                             cited_sources=[]),
    )

    agent = PersonaAgent(
        persona_id="buffett", client=fake,
        data_root=card_on_disk, in_memory_store=True,
    )
    monkeypatch.setattr(agent.store, "_embed",
                        lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    agent.store.add_chunks([
        CorpusChunk(id="c1", text="quality companies",
                    metadata={"source": "1986.pdf", "url": "u"}),
    ])

    conversation = PersonaConversation(
        entry_id="H-1", persona_id="buffett",
        started_at=datetime.now(UTC), messages=[],
    )
    user_text = "Should I buy this?"
    payload = {"thesis": "long XLE on supply shock"}

    msg = agent.chat(conversation=conversation,
                     user_text=user_text,
                     approval_payload=payload)
    assert msg.role == "assistant"
    assert msg.text.startswith("Hold quality")
    assert fake.stats.n_calls == 1
```

**Step 2: Run** — expect FAIL.

**Step 3: Implement**

```python
# src/castelino/agents/personas/agent.py
"""Per-turn persona chat: retrieval + system prompt + LLM call."""
from __future__ import annotations

import json
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
        # 1. Retrieve
        retrieval_q = (
            user_text + "\n[context] " + str(approval_payload.get("thesis", ""))
        )
        hits = self.store.query(retrieval_q, top_k=self.cfg.personas.retrieval_top_k)

        # 2. Append user message to thread
        user_msg = PersonaMessage(role="user", text=user_text,
                                  timestamp=datetime.now(UTC))
        conversation.messages.append(user_msg)

        # 3. Build prompt
        history_lines = "\n".join(
            f"{m.role.upper()}: {m.text}" for m in conversation.messages
        )
        user_prompt = f"{history_lines}\n\nRespond as {self.card.full_name}."

        # 4. LLM call
        resp: PersonaResponse = self.client.parse(
            model=self.cfg.personas.chat_model,
            system=self._system_prompt(hits),
            user=user_prompt,
            schema=PersonaResponse,
            max_tokens=600,
        )

        # 5. Map cited_sources back to Citation objects
        citations = []
        cited_set = set(resp.cited_sources)
        for h in hits:
            src = h.metadata.get("source", "")
            if src in cited_set:
                citations.append(Citation(source=src, snippet=h.text[:200],
                                          score=h.score))

        # 6. Append assistant message and return
        assistant_msg = PersonaMessage(
            role="assistant", text=resp.text,
            timestamp=datetime.now(UTC),
            citations=citations,
        )
        conversation.messages.append(assistant_msg)
        return assistant_msg
```

**Step 4: Run tests** — expect PASS.

**Step 5: Commit:** `feat(personas): PersonaAgent runtime with retrieval + cited LLM call`

---

## Task 11: `PersonaChatService` (queue integration)

**Files:**
- Create: `src/castelino/agents/personas/service.py`
- Test: `tests/test_personas_service.py`

The service is what dashboard endpoints will call. It handles the queue/load/save dance and finds-or-creates the conversation thread for a given (entry_id, persona_id) pair.

**Step 1: Failing test**

```python
# tests/test_personas_service.py
from datetime import datetime, UTC
from pathlib import Path

import pytest
import yaml

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.agent import PersonaResponse
from castelino.agents.personas.models import PersonaCard
from castelino.agents.personas.service import PersonaChatService
from castelino.orchestrator.approval import (
    ApprovalQueue, ApprovalItem, GateType,
)


@pytest.fixture
def queue_with_pending_item(tmp_path, monkeypatch):
    q = ApprovalQueue(state_dir=tmp_path)
    q.submit(gate=GateType.POST_HYPOTHESIS,
             payload={"thesis": "long XLE supply shock"},
             entry_id="H-test")

    # Save a fixture card
    import json
    card = PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="1965-present",
        belief_summary="quality forever",
        decision_framework=["margin of safety"],
        signature_phrases=[], famous_calls=[], voice_notes="folksy",
    )
    p = tmp_path / "agents" / "buffett" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))
    return q, tmp_path


def test_chat_service_appends_to_approval_item(queue_with_pending_item, monkeypatch):
    queue, data_root = queue_with_pending_item

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="Hold quality.",
                                               cited_sources=[]))

    svc = PersonaChatService(
        queue=queue, client=fake,
        data_root=data_root, in_memory_store=True,
    )
    monkeypatch.setattr("castelino.agents.personas.store.PersonaStore._embed",
                        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts])

    msg = svc.send(entry_id="H-test", persona_id="buffett",
                   user_text="What do you think?")
    assert msg.text == "Hold quality."

    # Persisted to the queue
    item = queue.get("H-test")
    assert len(item.conversations) == 1
    conv = item.conversations[0]
    assert conv.persona_id == "buffett"
    assert len(conv.messages) == 2  # user + assistant
```

**Step 2: Run** — expect FAIL.

**Step 3: Implement**

```python
# src/castelino/agents/personas/service.py
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
        # Persist back to queue
        self.queue._items[entry_id] = item
        self.queue._save()
        return msg

    def list_conversations(self, *, entry_id: str) -> list[PersonaConversation]:
        return self.queue.get(entry_id).conversations
```

**Step 4: Run tests** — expect PASS.

**Step 5: Commit:** `feat(personas): PersonaChatService — queue-integrated chat`

---

## Task 12: Panel orchestrator

**Files:**
- Create: `src/castelino/agents/personas/panel.py`
- Test: `tests/test_personas_panel.py`

**Step 1: Failing test**

```python
# tests/test_personas_panel.py
import asyncio
from datetime import datetime, UTC
from pathlib import Path

import pytest
import yaml

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.agent import PersonaResponse
from castelino.agents.personas.models import (
    Disagreement, PanelSynthesis, PersonaCard,
)
from castelino.agents.personas.panel import PanelOrchestrator
from castelino.orchestrator.approval import (
    ApprovalQueue, GateType,
)


@pytest.fixture
def queue_two_personas(tmp_path):
    import json
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
    # Check parallel: each persona got exactly 1 chat call
    assert n_persona_calls["n"] == 2

    # Persisted to ApprovalItem.panel_discussions
    item = queue.get("H-x")
    assert len(item.panel_discussions) == 1
```

**Step 2: Run** — expect FAIL.

**Step 3: Implement**

```python
# src/castelino/agents/personas/panel.py
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
        # Throwaway conversation per panel call — does not pollute the
        # 1:1 thread under approval.conversations[].
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

        # Step 1 — parallel fan-out
        responses = await asyncio.gather(*[
            self._ask_one(p, item, question) for p in personas
        ])

        # Step 2 — synthesis (sync LLM call)
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

        # Step 3 — persist
        panel = PanelDiscussion(
            entry_id=entry_id, question=question,
            responses=list(responses), synthesis=synthesis,
            created_at=datetime.now(UTC),
        )
        item.panel_discussions.append(panel)
        self.queue._items[entry_id] = item
        self.queue._save()
        return panel
```

**Step 4: Run tests** — expect PASS.

**Step 5: Commit:** `feat(personas): PanelOrchestrator — parallel fan-out + synthesis`

---

## Task 13: Dashboard backend endpoints

**Files:**
- Modify: `src/castelino/dashboard/endpoints/approvals.py` (extend)
- Create: `src/castelino/dashboard/endpoints/personas.py` (new file for /personas list/get)
- Modify: `src/castelino/dashboard/main.py` (mount new router)
- Test: `tests/test_personas_endpoints.py`

**Step 1: Failing test** — uses FastAPI's `TestClient`:

```python
# tests/test_personas_endpoints.py
import json
from datetime import datetime, UTC
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.agent import PersonaResponse
from castelino.agents.personas.models import (
    Disagreement, PanelSynthesis, PersonaCard,
)
from castelino.dashboard.main import app
from castelino.orchestrator.approval import ApprovalQueue, GateType


@pytest.fixture
def stubbed_dashboard(tmp_path, monkeypatch):
    # Stub data dirs
    monkeypatch.setenv("CASTELINO_DATA_DIR", str(tmp_path))

    queue = ApprovalQueue(state_dir=tmp_path)
    queue.submit(gate=GateType.POST_HYPOTHESIS,
                 payload={"thesis": "long XLE"}, entry_id="H-x")
    card = PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="t", belief_summary="b",
        decision_framework=[], signature_phrases=[], famous_calls=[],
        voice_notes="v",
    )
    p = tmp_path / "agents" / "buffett" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="Hold.", cited_sources=[]))
    monkeypatch.setattr("castelino.agents.base.get_llm_client", lambda: fake)
    monkeypatch.setattr("castelino.agents.personas.store.PersonaStore._embed",
                        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts])
    return TestClient(app), queue


def test_send_message_endpoint(stubbed_dashboard):
    client, queue = stubbed_dashboard
    r = client.post(
        "/approvals/H-x/conversations/buffett/messages",
        json={"text": "what do you think?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "assistant"
    assert "Hold" in body["text"]


def test_list_personas_endpoint(stubbed_dashboard):
    client, _ = stubbed_dashboard
    r = client.get("/personas")
    assert r.status_code == 200
    cards = r.json()
    assert any(c["persona_id"] == "buffett" for c in cards)
```

**Step 2: Run** — expect FAIL.

**Step 3: Implement** — extend `approvals.py`:

```python
# src/castelino/dashboard/endpoints/approvals.py — append

from pydantic import BaseModel

from castelino.agents.base import get_llm_client
from castelino.agents.personas.panel import PanelOrchestrator
from castelino.agents.personas.service import PersonaChatService


class _MessageBody(BaseModel):
    text: str


class _PanelBody(BaseModel):
    personas: list[str]
    question: str


def _chat_service():
    queue = ApprovalQueue()
    return PersonaChatService(queue=queue, client=get_llm_client())


def _panel_orchestrator():
    queue = ApprovalQueue()
    return PanelOrchestrator(queue=queue, client=get_llm_client())


@router.get("/approvals/{entry_id}/conversations")
def list_conversations(entry_id: str):
    return _chat_service().list_conversations(entry_id=entry_id)


@router.post("/approvals/{entry_id}/conversations/{persona_id}/messages")
def send_message(entry_id: str, persona_id: str, body: _MessageBody):
    return _chat_service().send(
        entry_id=entry_id, persona_id=persona_id, user_text=body.text,
    )


@router.post("/approvals/{entry_id}/panel")
async def run_panel(entry_id: str, body: _PanelBody):
    return await _panel_orchestrator().run(
        entry_id=entry_id, personas=body.personas, question=body.question,
    )
```

Create `src/castelino/dashboard/endpoints/personas.py`:

```python
"""Persona roster endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from castelino.agents.personas.models import PersonaCard
from castelino.config import get_settings

router = APIRouter()


def _agents_dir() -> Path:
    return Path("data/personas/agents")


@router.get("/personas")
def list_personas() -> list[PersonaCard]:
    cfg = get_settings()
    out = []
    for pid in cfg.personas.active_roster:
        p = _agents_dir() / pid / "profile.yaml"
        if p.exists():
            out.append(PersonaCard.model_validate(yaml.safe_load(p.read_text())))
    return out


@router.get("/personas/{persona_id}")
def get_persona(persona_id: str) -> PersonaCard:
    p = _agents_dir() / persona_id / "profile.yaml"
    if not p.exists():
        raise HTTPException(404, f"Persona {persona_id} not built")
    return PersonaCard.model_validate(yaml.safe_load(p.read_text()))
```

Mount in `src/castelino/dashboard/main.py`:

```python
from castelino.dashboard.endpoints import personas as personas_router
app.include_router(personas_router.router)
```

**Step 4: Run tests** — expect PASS.

**Step 5: Commit:** `feat(dashboard): persona conversations + panel + roster endpoints`

---

## Task 14: Frontend `usePersonaChat` + `usePanelDiscussion` hooks

**Files:**
- Create: `frontend/src/api/personas.ts` (typed client wrappers)
- Create: `frontend/src/hooks/usePersonaChat.ts`
- Create: `frontend/src/hooks/usePanelDiscussion.ts`
- Test: `frontend/src/hooks/__tests__/usePersonaChat.test.ts`

**Step 1: Failing test**

```typescript
// frontend/src/hooks/__tests__/usePersonaChat.test.ts
import { renderHook, act, waitFor } from "@testing-library/react";
import { usePersonaChat } from "../usePersonaChat";

beforeAll(() => {
  global.fetch = vi.fn() as any;
});

test("usePersonaChat sends a message and appends assistant reply", async () => {
  (global.fetch as any).mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      role: "assistant",
      text: "Hold quality.",
      timestamp: "2026-05-08T00:00:00Z",
      citations: [],
    }),
  });
  const { result } = renderHook(() => usePersonaChat("H-x", "buffett"));
  await act(async () => {
    await result.current.send("What do you think?");
  });
  await waitFor(() => {
    expect(result.current.messages.length).toBeGreaterThan(0);
  });
  expect(result.current.messages.at(-1)?.text).toBe("Hold quality.");
});
```

**Step 2: Run** `cd frontend && npm test`. Expect FAIL.

**Step 3: Implement**

```typescript
// frontend/src/api/personas.ts
import { Citation, PersonaMessage, PersonaCard, PanelDiscussion } from "./types";

export async function sendPersonaMessage(
  entryId: string, personaId: string, text: string
): Promise<PersonaMessage> {
  const r = await fetch(
    `/approvals/${entryId}/conversations/${personaId}/messages`,
    { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }) },
  );
  if (!r.ok) throw new Error(`send failed: ${r.status}`);
  return r.json();
}

export async function runPanel(
  entryId: string, personas: string[], question: string,
): Promise<PanelDiscussion> {
  const r = await fetch(`/approvals/${entryId}/panel`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ personas, question }),
  });
  if (!r.ok) throw new Error(`panel failed: ${r.status}`);
  return r.json();
}

export async function listPersonas(): Promise<PersonaCard[]> {
  const r = await fetch("/personas");
  if (!r.ok) throw new Error(`personas failed: ${r.status}`);
  return r.json();
}
```

```typescript
// frontend/src/hooks/usePersonaChat.ts
import { useCallback, useState } from "react";
import { sendPersonaMessage } from "../api/personas";
import { PersonaMessage } from "../api/types";

export function usePersonaChat(entryId: string, personaId: string) {
  const [messages, setMessages] = useState<PersonaMessage[]>([]);
  const [pending, setPending] = useState(false);

  const send = useCallback(
    async (text: string) => {
      setPending(true);
      const userMsg: PersonaMessage = {
        role: "user", text, timestamp: new Date().toISOString(), citations: [],
      };
      setMessages((m) => [...m, userMsg]);
      try {
        const reply = await sendPersonaMessage(entryId, personaId, text);
        setMessages((m) => [...m, reply]);
      } finally {
        setPending(false);
      }
    },
    [entryId, personaId],
  );

  return { messages, pending, send };
}
```

```typescript
// frontend/src/hooks/usePanelDiscussion.ts
import { useCallback, useState } from "react";
import { runPanel } from "../api/personas";
import { PanelDiscussion } from "../api/types";

export function usePanelDiscussion(entryId: string) {
  const [panel, setPanel] = useState<PanelDiscussion | null>(null);
  const [pending, setPending] = useState(false);

  const run = useCallback(
    async (personas: string[], question: string) => {
      setPending(true);
      try {
        setPanel(await runPanel(entryId, personas, question));
      } finally {
        setPending(false);
      }
    },
    [entryId],
  );

  return { panel, pending, run };
}
```

Add the new types to `frontend/src/api/types.ts`:

```typescript
export interface Citation { source: string; snippet: string; score: number; }
export interface PersonaMessage {
  role: "user" | "assistant";
  text: string;
  timestamp: string;
  citations: Citation[];
}
export interface PersonaCard {
  persona_id: string; full_name: string; role: string; tenure: string;
  belief_summary: string; decision_framework: string[];
  signature_phrases: string[]; voice_notes: string;
}
export interface PanelResponse { persona_id: string; text: string; citations: Citation[]; }
export interface Disagreement { axis: string; positions: Record<string, string>; }
export interface PanelSynthesis {
  consensus: string[]; disagreements: Disagreement[];
  strongest_objection: string; recommended_modifications: string[];
}
export interface PanelDiscussion {
  entry_id: string; question: string;
  responses: PanelResponse[]; synthesis: PanelSynthesis; created_at: string;
}
```

**Step 4: Run tests** — expect PASS.

**Step 5: Commit:** `feat(frontend): persona-chat + panel API hooks + types`

---

## Task 15: `PersonaPicker` component

**Files:**
- Create: `frontend/src/components/PersonaPicker.tsx`
- Test: `frontend/src/components/__tests__/PersonaPicker.test.tsx`

Renders the roster from `GET /personas`. Radio-style selection, role badges. ~80 lines of TSX. Test asserts:
- Loading state visible while fetching
- Options render after fetch (mocked)
- `onChange(persona_id)` fires on click

Commit: `feat(frontend): PersonaPicker component`

---

## Task 16: `PersonaChat` component

**Files:**
- Create: `frontend/src/components/PersonaChat.tsx`
- Test: `frontend/src/components/__tests__/PersonaChat.test.tsx`

Message thread + input box + citation footnotes. Wraps `usePersonaChat`. Test asserts:
- Submitting text calls `send`
- Assistant messages render with superscript citation links
- Hover/tap on citation reveals snippet

Commit: `feat(frontend): PersonaChat component with citation footnotes`

---

## Task 17: `PanelDiscussionModal` component

**Files:**
- Create: `frontend/src/components/PanelDiscussionModal.tsx`
- Test: `frontend/src/components/__tests__/PanelDiscussionModal.test.tsx`

Modal with personas selection (multi-select), question input, "Run" button. After completion shows the per-persona response cards + synthesis section. "Apply Synthesis" button copies the synthesis text into a callback (parent uses it to update the decision-notes field).

Commit: `feat(frontend): PanelDiscussionModal with apply-synthesis`

---

## Task 18: `ApprovalConsultPage` route

**Files:**
- Create: `frontend/src/pages/ApprovalConsultPage.tsx`
- Modify: `frontend/src/App.tsx` (add route `/approvals/:entryId/consult`)
- Modify: `frontend/src/pages/ApprovalCenterPage.tsx` (add "Consult" button per pending item linking to the new route)

Three-column layout per Section 5 of the design doc. Wires together `PersonaPicker`, `PersonaChat`, the existing decision controls, and `PanelDiscussionModal`. ~150 lines of TSX.

Commit: `feat(frontend): /approvals/:id/consult page wiring everything together`

---

## Task 19: Remaining persona scrapers

For each persona in the v1 roster (after Buffett ships), this is a new task:

- T19a: `personas/scrapers/krugman.py` — NYT archive RSS + page scrape
- T19b: `personas/scrapers/el_erian.py` — Project Syndicate + LinkedIn
- T19c: `personas/scrapers/summers.py` — Project Syndicate + Brookings + Macro Musings transcripts
- T19d: `personas/scrapers/druckenmiller.py` — `youtube-transcript-api` for known interviews (Bloomberg, CNBC, Sohn, Robin Hood)
- T19e: `personas/scrapers/dalio.py` — PDF reader for *Principles* + *Big Debt Crises*; LinkedIn essays
- T19f: `personas/scrapers/tudor_jones.py` — `youtube-transcript-api` for Robin Hood, Real Vision, Davos panels; *Trader* (1987) transcript

Each follows the Buffett pattern (Task 7): fixture-based unit test → implementation → register in `SCRAPERS_REGISTRY`. Each commit independently.

**For Druckenmiller and Tudor Jones:** add `youtube-transcript-api>=0.6,<1` to `pyproject.toml`. Test patches the API call; CI doesn't need YouTube access.

Suggested commit messages:
- `feat(personas): Krugman scraper (NYT archive)`
- `feat(personas): El-Erian scraper (Project Syndicate + LinkedIn)`
- ... etc

---

## Task 20: CLAUDE.md + learnings

**Files:**
- Modify: `CLAUDE.md` (append entry under `## Completed Work`)
- Modify: `learnings.md` (any gotchas surfaced during impl)

Append to `CLAUDE.md`:

```markdown
### 2026-05-08 — Persona Agents (HITL consultation chat)
- New module `src/castelino/agents/personas/` lets the human consult
  RAG-backed simulated economists & investors during approval gates
- Roster v1: Krugman, El-Erian, Summers, Buffett, Druckenmiller, Dalio,
  Tudor Jones. Each has a corpus of public writings scraped + chunked
  + embedded into a per-persona Chroma collection
- Per-turn retrieval: query embedded → top-k chunks → system prompt
  with profile card + chunks → LLM call returning text + cited sources
- Panel mode: parallel fan-out across N personas + synthesis pass
  surfaces consensus, disagreement, strongest objection, recommended
  modifications
- Conversations attach to ApprovalItem.conversations[]; full audit
  trail preserved with each approval
- New CLI: `castelino persona-build --persona buffett --full-name "Warren Buffett" --role "Value investor"`
- New dashboard route /approvals/:id/consult (Vite/React)
- Design doc: `docs/plans/2026-05-08-persona-agents-design.md`
- Implementation plan: `docs/plans/2026-05-08-persona-agents-plan.md`
```

Commit: `docs: log persona-agents completion + learnings`

---

## Definition of done

- All Python tests pass: `pytest tests/test_personas_*.py`
- All frontend tests pass: `cd frontend && npm test`
- `castelino persona-build --persona buffett --full-name "Warren Buffett" --role "Value investor"` runs end-to-end against the live Berkshire site (or its fixtures), produces `data/personas/agents/buffett/profile.yaml` and a populated Chroma collection
- Dashboard at `/approvals/:entry_id/consult` loads, persona picker shows the roster, sending a message returns an assistant reply with citations, "Run Panel Discussion" returns a synthesis
- All commits individually green
