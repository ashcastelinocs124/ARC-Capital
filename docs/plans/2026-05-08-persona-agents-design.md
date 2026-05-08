# Persona Agents — Design Doc

**Date:** 2026-05-08
**Branch:** `persona-agent`
**Status:** Design approved, ready for implementation planning

---

## Goal

Let the human consult simulated economists and market investors during the
existing HITL approval gates (`POST_HYPOTHESIS`, `POST_DEBATE`) before
approving, editing, or rejecting a pipeline decision. Conversations happen
through the dashboard; transcripts are part of the audit trail.

The point is to **expose the human to varied viewpoints** before they
commit to a decision — not to replace the agent pipeline's internal Bull /
Bear / Debate loop. Personas are advisors, not voters.

## Non-goals

- Personas don't participate in the agent pipeline. They're never invoked
  inside the orchestrator graph; they're only invoked from the dashboard
  approval-review page.
- No persona memory across approvals. Each chat is scoped to one
  `ApprovalItem`.
- Not a chatbot for free-form market chitchat — chat is anchored to a
  pending approval payload.
- No voice/audio. Text only.
- English only.

## Architecture

Three layers under `src/castelino/agents/personas/` plus dashboard
integration. Mirrors the structure of the speech listener (offline build →
online runtime → integration).

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1 — Corpus Builder         (offline, on-demand / cron)       │
│  Per persona, scrape primary sources. Chunk + embed → Chroma        │
│  collection. Auto-generate profile card.                            │
│  Output: data/personas/agents/<id>/{profile.yaml, ...}              │
│          data/personas/chroma/<id>/                                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 2 — PersonaAgent runtime    (online, per-turn)               │
│  Embed user message + approval payload → retrieve top-k corpus      │
│  chunks → build prompt with profile card + retrieved chunks → LLM   │
│  call → response with citations.                                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3 — Persistence + Panel orchestrator                         │
│  Conversations attach to ApprovalItem.conversations[].              │
│  Panel: parallel fan-out across 3-4 personas, then a synthesis      │
│  pass surfaces agreement, disagreement, strongest objection.        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                Dashboard frontend (existing Vite/React)
                /approvals/:id/consult page with persona picker,
                chat thread, "Run Panel Discussion" button.
```

## Data shapes

### Per-conversation models

```python
class Citation(BaseModel):
    source: str          # "buffett_letters_2008.pdf#p4"
    snippet: str         # exact text quoted
    score: float         # retrieval similarity, 0-1


class PersonaMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    timestamp: datetime
    citations: list[Citation] = Field(default_factory=list)


class PersonaConversation(BaseModel):
    entry_id: str        # the ApprovalItem this thread belongs to
    persona_id: str      # "buffett" | "druckenmiller" | ...
    started_at: datetime
    messages: list[PersonaMessage]
```

### Panel models

```python
class PanelResponse(BaseModel):
    persona_id: str
    text: str
    citations: list[Citation]


class Disagreement(BaseModel):
    axis: str                       # "sizing", "horizon", "regime read"
    positions: dict[str, str]       # persona_id -> their stance


class PanelSynthesis(BaseModel):
    consensus: list[str]
    disagreements: list[Disagreement]
    strongest_objection: str
    recommended_modifications: list[str]


class PanelDiscussion(BaseModel):
    entry_id: str
    question: str
    responses: list[PanelResponse]
    synthesis: PanelSynthesis
    created_at: datetime
```

### Profile card (the durable per-persona artifact)

```python
class FamousCall(BaseModel):
    date: str                       # "1992-09" or "2008"
    description: str

class PersonaCard(BaseModel):
    persona_id: str
    full_name: str
    role: str                       # "Macro speculator, ex-Duquesne"
    tenure: str
    belief_summary: str             # 200-word distillation, LLM-generated
    decision_framework: list[str]
    signature_phrases: list[str]
    famous_calls: list[FamousCall]
    voice_notes: str                # tone / cadence
```

### Existing `ApprovalItem` extension

```python
class ApprovalItem(BaseModel):
    # ... existing fields ...
    conversations: list[PersonaConversation] = Field(default_factory=list)
    panel_discussions: list[PanelDiscussion] = Field(default_factory=list)
```

The conversation history goes into `data/approval_queue.json` alongside
the approval. When the human approves/rejects, the chat is preserved as
part of the decision audit trail.

## Layer 1 — Corpus builder

### Per-persona scraper

```
personas/scrapers/
├── base.py              # PersonaScraper ABC: async fetch() -> list[CorpusDoc]
├── buffett.py           # GETs berkshirehathaway.com letters, extracts PDF text
├── krugman.py           # NYT archive RSS + page scrape
├── el_erian.py          # Project Syndicate + LinkedIn
├── summers.py           # Project Syndicate + Brookings + podcast transcripts
├── druckenmiller.py     # YouTube transcript dl for known interviews
├── dalio.py             # PDF reader (Principles, Big Debt Crises) + LinkedIn
└── tudor_jones.py       # YouTube transcript dl + Real Vision + Robin Hood
```

All return `CorpusDoc(source, date, title, text, url)` — heterogeneous
sources, single output type. Same pattern as the speech listener's Fed
scraper.

### Chunking + embedding

```python
async def build_persona(persona_id: str) -> None:
    scraper = SCRAPERS[persona_id]()
    docs = await scraper.fetch()
    chunks = chunk_docs(docs, max_tokens=400, overlap=50)

    collection = chroma.get_or_create_collection(persona_id)
    for batch in batches(chunks, 100):
        embeddings = await embed_batch([c.text for c in batch])
        collection.add(
            ids=[c.id for c in batch],
            embeddings=embeddings,
            metadatas=[c.metadata for c in batch],
            documents=[c.text for c in batch],
        )

    sample = stratified_sample(chunks, n=30)        # spread across decades
    card = await generate_profile_card(persona_id, sample)
    save_profile_card(persona_id, card)
```

### Refresh cadence

On-demand via `castelino persona-build --persona <id>`. Buffett
(annual letters) ⇒ yearly. Krugman (daily op-eds) ⇒ weekly. Configurable
per-persona; default is monthly.

### v1 roster

| Persona | Role | Sources |
|---|---|---|
| Paul Krugman | Keynesian economist, NYT | NYT archive, MIT papers, *Return of Depression Economics* |
| Mohamed El-Erian | Allianz advisor | Bloomberg/FT op-eds, LinkedIn, *When Markets Collide* |
| Larry Summers | Former Treasury Sec | Project Syndicate, Brookings, Macro Musings transcripts |
| Warren Buffett | Value investor | Annual shareholder letters 1977–present |
| Stanley Druckenmiller | Macro speculator | Bloomberg/CNBC/Sohn/Robin Hood transcripts |
| Ray Dalio | Bridgewater | *Principles*, *Big Debt Crises*, LinkedIn essays |
| Paul Tudor Jones | Macro trader | Robin Hood / Real Vision / *Trader* (1987) / Davos transcripts |

## Layer 2 — PersonaAgent runtime

```
┌──────────────────────────────────────────────────────────────────────┐
│ POST /approvals/:entry_id/conversations/:persona_id/messages          │
│ body: { "text": "How would you size this if vol just hit 45?" }      │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PersonaChatService.send(approval_id, persona_id, user_text)         │
│  --------------------------------------------------------------      │
│  1. Load ApprovalItem from queue                                     │
│  2. Find or create conversation thread for (entry_id, persona_id)    │
│  3. Append user message → thread                                     │
│  4. Embed (user_text + payload.thesis) → vector                      │
│  5. Chroma query: top_k=6 chunks from persona's collection           │
│  6. Build prompt:                                                    │
│       system = profile_card.system_prompt                            │
│              + "Cite from these passages when relevant:\n"           │
│              + "\n---\n".join(chunks)                                │
│              + "\nRespond as <persona_name>. Voice: <traits>.\n"     │
│              + "Stay in character. If asked something outside your   │
│                 expertise, say so honestly."                         │
│       messages = [system] + thread.messages + [user_text]            │
│  7. LLM call → assistant text + citations actually quoted            │
│  8. Append assistant message → thread; persist queue                 │
│  9. Return PersonaMessage                                            │
└──────────────────────────────────────────────────────────────────────┘
```

**Why retrieval per turn:** the user's question shifts what's relevant.
Q1 wants macro-level chunks; Q5 might want sizing rules. Re-retrieving
keeps the persona grounded as the conversation moves.

## Layer 3 — Persistence + Panel orchestrator

### Persistence

Conversations live inside the existing `data/approval_queue.json` as
`ApprovalItem.conversations[]`. When approve/reject lands, the chat is
preserved with the decision. Other agents (e.g. the curator) can later
read the transcript and ingest insights into the long-term lessons
journal.

### Panel orchestrator

```
POST /approvals/:entry_id/panel
body: { "personas": ["buffett","druckenmiller","krugman","dalio"],
        "question": "Is this thesis sound? What would you change?" }
```

Pipeline:

1. **Independent views (parallel):** `asyncio.gather` — each persona
   answers the same question with their own retrieval, NOT seeing the
   others' responses. Keeps diversity intact.
2. **Synthesis (one LLM call):** facilitator-prompted, returns
   `PanelSynthesis` with consensus / disagreements / strongest objection
   / recommended modifications.
3. **Store:** append `PanelDiscussion` to `approval.panel_discussions[]`.
   Each persona's response is also written as a one-message thread into
   `approval.conversations[]` so the human can drill into any individual.

**Why parallel-then-synthesize, not group chat:** if personas saw each
other's drafts in real-time they'd anchor on whoever speaks first and
diversity collapses (academic Delphi panels handle this the same way).

**Why one synthesis pass and not iterative debate:** debate is the
existing Bull/Bear architecture. Panels are for *exposing the human to
varied viewpoints*, not for arriving at a verdict on their own.

**Cost shape:** ~4 × `gpt-4o-mini` (~$0.0008 each) + 1 × `gpt-4o`
(~$0.01) ≈ ~$0.013 per panel.

## Dashboard UI

### New route

`/approvals/:entry_id/consult` — reached from the existing approval
center via a new "Consult" button on each pending item.

### Layout

Three columns: pending-item summary (left), persona picker + "Run Panel"
button (top-right), chat thread (bottom-right). Decision controls
(Approve / Reject / Edit + notes) stay in the left column for proximity
to the pending item.

### Citations

Assistant messages show numbered superscripts; hovering reveals the
snippet + source link. Lets the human verify the persona isn't
hallucinating. Citation = `Citation(source, snippet, score)` from the
retrieved chunks that the LLM actually quoted.

### Panel discussion modal

Triggered by "Run Panel Discussion" — shows each persona's response
side-by-side, then the synthesis panel below with consensus,
disagreements, strongest objection, and recommended modifications.
"Apply Synthesis" copies the synthesis text into the human's
decision-notes field.

### Components

```
frontend/src/
├── pages/ApprovalConsultPage.tsx          (the full page)
├── components/PersonaPicker.tsx
├── components/PersonaChat.tsx
├── components/PanelDiscussionModal.tsx
├── hooks/usePersonaChat.ts
└── hooks/usePanelDiscussion.ts
```

### New backend endpoints

```
GET    /approvals/:id/conversations
POST   /approvals/:id/conversations/:persona_id/messages
POST   /approvals/:id/panel
GET    /personas
GET    /personas/:id
```

## Configuration

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

## File layout

```
data/personas/
├── agents/
│   ├── buffett/
│   │   ├── profile.yaml          (auto-generated card, human-editable)
│   │   ├── corpus_manifest.json  (source URLs + last-fetched timestamps)
│   │   └── chunks/               (raw chunks pre-embedding, debugging)
│   ├── ... (one dir per persona) ...
│   └── tudor_jones/
├── chroma/                        (one Chroma collection per persona_id)
└── (existing) <speaker_id>.json  (speech-listener personas — separate)
```

The speech-listener `data/personas/<speaker_id>.json` files (Powell etc.)
and the new `data/personas/agents/<persona_id>/` are intentionally
namespaced — different concepts, no collision.

## Testing

| Layer | Test type | Coverage |
|---|---|---|
| Scrapers | Unit + fixture HTML/PDF | Each scraper parses fixtures correctly |
| Chunker | Unit | Token counts, overlap, source metadata preserved |
| Card generator | Unit (mocked LLM) | Generates valid `PersonaCard` from fixture chunks |
| `PersonaAgent.chat()` | Unit (FakeLLMClient + in-mem Chroma) | Retrieval, prompt building, threading |
| Panel orchestrator | Unit (FakeLLMClient) | Parallel fan-out, synthesis schema, persistence |
| `ApprovalItem.conversations` | Unit | JSON round-trip, append-only invariant |
| Dashboard endpoints | FastAPI TestClient | All 5 new endpoints |
| Frontend components | Vitest + RTL | Picker, chat UI, panel modal, citations |
| End-to-end | Playwright | Approve flow with consult, panel, apply synthesis |

In-memory Chroma keeps unit tests fast.

## Rollout

1. Build infrastructure first (models, runtime, orchestrator, endpoints,
   frontend) behind feature flag (`personas.enabled: false` default).
2. Build **one persona end-to-end (Buffett)** — smallest cleanest corpus
   (PDF letters). Validates the architecture before scaling.
3. Add other personas one at a time via `castelino persona-build`.
4. Enable feature flag in production config.
5. Monthly cron rebuilds personas (per-persona cadence).

## Failure modes

| Failure | Effect | Mitigation |
|---|---|---|
| Scraper breaks (site change) | Corpus stale | persona-build exits non-zero; last-good corpus stays usable |
| LLM hallucinates outside corpus | Trust loss | Citations make hallucinations visible; voice notes include "if outside scope, say so" |
| Chroma DB corrupted | Chat fails | persona-build is idempotent — rerun for that persona |
| Embedding API down | Retrieval fails | Cache last-N queries per session; fall back to card-only mode |
| Rate-limit during panel fan-out | Slow panel | Backoff with jitter (existing pattern) |
| Card drift from reality | Stale advice | Monthly rebuild; profile.yaml is git-tracked, diffable |

## Open questions

- **Persona naming legality:** all seven are public figures; their
  primary writings are publicly available. Corpus is for personal
  research/decision-support, not redistributed. Worth a project-level
  policy note but not a blocker.
- **Citation truthfulness:** the LLM picks which retrieved chunks to
  cite. If it cites a chunk it didn't actually quote from, that's a
  fidelity bug. v2 work — possibly enforce via a structured-output
  schema where citations are first-class outputs of the call.
- **Panel composition heuristic:** v1 has the human pick which 3-4
  personas join the panel. v2 could auto-pick based on the approval
  payload (e.g. "stagflation thesis ⇒ pick Krugman, Dalio, El-Erian, PTJ
  by default") but premature without usage data.

## Out of scope (v2+)

- Persona memory across approvals (each chat is per `ApprovalItem`)
- Voice/audio chat
- Real-time persona reactions inside the agent pipeline
- User-uploaded persona corpora
- Multi-language
- Auto-generated persona panel composition
