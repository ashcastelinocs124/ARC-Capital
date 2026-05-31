# Deep Research Agent — Design

**Date:** 2026-05-30
**Status:** Approved (brainstorming complete; implementation plan next)
**Author:** Ashley Castelino (with Claude)

## 1. Summary & placement

A human-driven, multi-agent **deep-research engine** that takes an analyst's raw
query, rewords it, asks clarifying questions, waits for answers, decomposes the
enriched query into parallel sub-questions, researches each via **Perplexity
Sonar** concurrently, then synthesizes a **cited report** with a bounded
**reflection loop** that fills gaps.

- **Home:** `src/castelino/agents/research/deep/`
- **Consumer:** a human analyst (standalone analyst tool). Reports persist to
  disk and are **NOT** auto-fed into the trading pipeline. (Attaching a report
  to an `ApprovalItem` is a deferred follow-up, not in scope here.)
- **Reuses existing primitives:**
  - `StructuredAgent` / `OpenAIClient` / `FakeLLMClient` (`agents/base.py`)
  - The persona panel's `asyncio.gather` fan-out pattern (`agents/personas/panel.py`)
  - Tiered model config (`models.reasoning` / `models.fast`, `config.py`)
  - The Sonar call pattern (`triggers/news.py`, `triggers/calendar.py`,
    `agents/personas/sonar_fetcher.py`)

### Decisions locked during brainstorming
1. Purpose: fund research engine, human-invoked (analyst tool).
2. Search backend: reuse **Perplexity Sonar** (one call = search + read + cite).
3. Surface: **both** CLI and dashboard, one shared engine.
4. Clarify loop: **interactive / blocking** (human answers before research runs).
5. Depth: **iterative with reflection** (synthesizer can trigger a 2nd round).
6. Decomposition: **dynamic, hard-capped** (lead decides N, capped at 6).
7. Output: **structured cited report** (Pydantic); `exec_summary` carries the prose.
8. Session model: **stateful resumable session** (state machine, both surfaces).
9. Persistence: **persist to disk**, standalone (`data/research/<id>.json`).
10. Cost: **hard caps + global Sonar budget + concurrency semaphore**.
11. Orchestration: **plain asyncio orchestrator**, tiered models (no LangGraph).

## 2. Agents (roles)

| Agent | Tier | Job |
|---|---|---|
| **Clarifier** | reasoning | Reword raw query into a precise research question + generate ≤3 clarifying questions (each with rationale). |
| **Lead** (decomposer) | reasoning | Take reworded query + answers → break into N≤6 sub-questions with rationale. On round 2, decomposes only the reflection gaps. |
| **Sub-agent** (×N parallel) | fast | Research one sub-question via Sonar → return a `SubFinding` with citations. |
| **Synthesizer** | reasoning | Merge findings → draft report **and** reflect: list gaps, decide if a 2nd round is warranted. |

## 3. Orchestration & flow

Plain **asyncio orchestrator** modeled as a state machine. No LangGraph —
matches the persona-panel precedent, easier to unit-test, decoupled from the
trading DAG.

```
CREATED
  → [Clarifier] rewords + asks questions
AWAITING_ANSWERS  ⏸ (blocks for human)
  → (analyst answers)
RESEARCHING
  → [Lead] decomposes → asyncio.gather over sub-agents
    (each sub-agent = Sonar call(s), bounded by a concurrency semaphore)
SYNTHESIZING
  → [Synthesizer] drafts + reflects
    ├─ gaps & round < max_rounds & budget left → RESEARCHING (round 2, gap sub-questions only)
    └─ else → COMPLETE
COMPLETE  (persist to data/research/<id>.json)   |   FAILED (reason)
```

## 4. Data model (Pydantic)

- **`ResearchSession`** — `id`, `original_query`, `reworded_query`, `status`,
  `clarifying_questions[]`, `answers{}`, `sub_questions[]`, `rounds[]`,
  `report`, `created_at`, `updated_at`, `sonar_calls_used`.
- **`ClarificationQuestion`** — `question`, `why`.
- **`SubQuestion`** — `id`, `text`, `rationale`, `round`.
- **`SubFinding`** — `sub_question_id`, `summary`, `key_points[]`,
  `citations[]`, `confidence` (0-1), `error?`.
- **`Citation`** — `title`, `url`, `snippet`. (Reuse the persona `Citation`
  type if field-compatible; otherwise a sibling model.)
- **`ReflectionResult`** — `is_sufficient`, `gaps[]`, `new_sub_questions[]`.
- **`DeepResearchReport`** — `exec_summary` (human-readable explanation),
  `findings[]`, `sources[]` (deduped union of citations), `confidence`,
  `caveats[]`, `gaps_remaining[]`.

The structured report carries the prose explanation in `exec_summary`, so no
separate prose layer is needed — CLI prints it; dashboard renders the rest.

## 5. Surfaces (stateful resumable session)

One engine, two front-ends.

**CLI:** `castelino research "<query>"`
- Prints reworded query + clarifying questions, reads answers from stdin,
  streams progress, prints `exec_summary` + sources.
- `--no-clarify` flag: auto-assume context (Clarifier states assumptions),
  run end-to-end without blocking — for scripting.

**Dashboard:** new `DeepResearchPage` (React) + endpoints in
`dashboard/endpoints/research.py`:
- `POST /research/start` → `{session_id, reworded_query, clarifying_questions}` (pauses)
- `POST /research/{id}/answers` → starts research in background, returns `{status: RESEARCHING}`
- `GET /research/{id}` → poll session/report until `COMPLETE`
- `GET /research` → list past reports

Background + poll (not a long blocking HTTP request); fits the state machine.

## 6. Cost guardrails

New `deep_research:` block in `config.yaml` (typed `DeepResearchCfg` in
`config.py`):

| Knob | Default | Meaning |
|---|---|---|
| `max_sub_questions` | 6 | hard cap on decomposition fan-out |
| `max_rounds` | 2 | reflection rounds (incl. first) |
| `max_sonar_calls` | 15 | global Sonar budget per report |
| `concurrency` | 5 | asyncio semaphore over sub-agents |
| `clarify_max_questions` | 3 | cap on clarifying questions |

Worst-case spend per report is tightly bounded and tunable like the other knobs.

## 7. Error handling

- A Sonar failure → sub-agent returns an empty/flagged `SubFinding`; the run
  continues (matches the existing "returns [] on failure" convention). **All**
  sub-agents failing in a round → `FAILED`.
- LLM calls reuse `OpenAIClient` retries; Sonar gets bounded retries.
- Budget exhausted mid-run → stop spawning, synthesize with what's gathered,
  note it in `caveats` / `gaps_remaining`.
- Session store uses **atomic write** (temp file + `os.replace`) — learnings
  note corrupt-cache JSON from partial writes, so this avoids half-written
  sessions.

## 8. Testing

- Reuse `FakeLLMClient` (register handlers per agent schema:
  Clarifier/Lead/Synthesizer) + an **injectable `FakeSonarClient`** returning
  canned findings → fully deterministic, no network.
- Coverage:
  - Per-agent unit tests (prompt builds, schema parse).
  - Orchestrator: fan-out count respects cap; reflection triggers round 2;
    budget stop mid-run; all-sub-agents-fail → `FAILED`.
  - State-machine transition tests (CREATED → AWAITING_ANSWERS → … → COMPLETE).
  - Session store round-trip (atomic write + reload).
- Live tests (`@pytest.mark.live`) hit real OpenAI + Sonar, skipped in CI.

## 9. Known caveat (not a blocker)

`config.yaml` sets live tiers to `gpt-5.5` / `gpt-5.4-mini`, which are not real
OpenAI model IDs. This engine inherits whatever those resolve to via
`_resolve_model_id`. Worth fixing before live runs, but orthogonal to this
design.

## 10. Out of scope (deferred)

- Attaching a report to an `ApprovalItem` (HITL coupling).
- Raw search-API + fetch + read backend (Tavily/Exa); Sonar only for v1.
- WebSocket live streaming of sub-agent progress (polling for v1).
- Auto-invocation from the trading pipeline.
