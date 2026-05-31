# Castelino-Capital

A mini multi-agent hedge fund system. Currently in brainstorming/architecture phase.

## Git push policy (HARD RULE)

Every push to a remote MUST go through the `/gitpush` skill. Never run `git push`, `gh repo create --push`, or any other push-equivalent directly in Bash, even for "simple" pushes to an already-tracked branch. The skill runs a pre-push secret scan (env files, `.pem`/`.key` files, credentials in diff hunks) that raw `git push` skips. If a push happens outside the skill, log it in `learnings.md` and run `/gitpush` retroactively against the pushed branch as an audit.

## Learnings

This project maintains a `learnings.md` file at the project root. Add entries whenever you discover something interesting. Each entry must include a **Ref** subtitle pointing to the relevant CLAUDE.md section. Only read `learnings.md` when its contents are directly relevant to the current task.

Use the `/capture-learnings` skill at the end of sessions to do this automatically.

## Memory System

### Short-term memory (`short_term_memory.md`)
Holds a detailed log of the **past 5 immediate tasks** — what was done, why, and the outcome. When a new task is completed, append it. If there are more than 5 entries, summarize the oldest one into `long_term_memory.md` before removing it.

### Long-term memory (`long_term_memory.md`)
When a task ages out of short-term memory, write a **condensed summary** (2-3 lines) here. This preserves historical context without clutter.

**Pruning rule:** Every 10 sessions, review `long_term_memory.md` against `CLAUDE.md`. Delete any entries no longer relevant to the current state of the project.

### Loading priority
At the start of every session, read both files into context:
1. **`short_term_memory.md` first** — most important, give it higher weight.
2. **`long_term_memory.md` second** — background context, defer to short-term when there's conflict.

## Architecture (proposed, evolving)

Multi-agent system inspired by an analyst desk:
- **Current Event Agent** → ingests news/macro signals
- **Macro Hypothesis Agent** → forms market thesis
- **Bull Agent / Bear Agent** → opposing views, each backed by Technical Analysis, Backtesting, Web, Risk sub-agents
- **Debate Agent** → adjudicates Bull vs Bear
- **Portfolio Agent** → translates verdict into positions
- **Portfolio** → execution / state

This is a starting point. The brainstorming session is exploring variations.

## Completed Work

### 2026-05-30 — Deep Research Agent
- Multi-agent, Sonar-backed deep-research engine under `src/castelino/agents/research/deep/`: raw query → Clarifier (reword + clarifying questions) → Lead (decompose into ≤6 sub-questions) → parallel Sub-agents (Perplexity Sonar + LLM distill) → Synthesizer with bounded reflection loop (≤2 rounds) → cited `DeepResearchReport`
- Plain `asyncio` orchestrator as a state machine (CREATED→AWAITING_ANSWERS→RESEARCHING→SYNTHESIZING→COMPLETE/FAILED); fan-out via `asyncio.gather` + `Semaphore`; NO LangGraph. Reuses `StructuredAgent`/`OpenAIClient`/`FakeLLMClient` and the persona-panel parallelism pattern
- Cost caps in `config.yaml::deep_research` (max_sub_questions=6, max_rounds=2, max_sonar_calls=15, concurrency=5, clarify_max_questions=3); tiered models (reasoning for clarifier/lead/synthesizer, fast for sub-agents)
- Reports persist to `data/research/<id>.json` (atomic write); analyst tool, NOT auto-fed into the trading pipeline
- Surfaces: CLI `castelino research "<q>" [--no-clarify]` and dashboard (router `dashboard/endpoints/deep_research.py`: POST /research/start, POST /research/{id}/answers [background], GET /research/{id}, GET /research) + React page at `/deep-research` (`frontend/src/pages/DeepResearchPage.tsx`)
- 15 test files (`tests/test_deep_research_*.py`), all green; deterministic via FakeLLMClient + FakeSonarClient
- Design: `docs/plans/2026-05-30-deep-research-agent-design.md`; plan: `docs/plans/2026-05-30-deep-research-agent.md`

### 2026-05-05 — OpenBB Integration
- Integrated OpenBB Platform SDK as primary data source with yfinance/FRED fallback (`src/castelino/data/openbb_adapter.py`)
- Built 6-tab OpenBB Workspace dashboard (FastAPI backend at port 7779, 22 widgets)
- Added human-in-the-loop approval gates (post-hypothesis, post-debate) — pipeline stalls until CLI approval
- New CLI commands: `castelino serve`, `castelino queue`, `castelino approve`, `castelino reject`, `castelino edit`
- Dashboard tabs: Portfolio, Macro & Signals, Research & Technicals, Risk & Attribution, Agent Decisions, Approval Queue
- Research agents (TA, risk, web) now pull data from OpenBB with pandas fallback
- Design doc: `docs/plans/2026-05-05-openbb-integration-design.md`

### 2026-05-08 — Persona Agents (HITL consultation chat)
- New module `src/castelino/agents/personas/` lets the human consult RAG-backed simulated economists & investors during approval gates
- v1 roster (config-driven, macro-only): Krugman, El-Erian, Summers, Druckenmiller, Dalio, Tudor Jones. Buffett (value investor) intentionally excluded from the macro fund's roster, but his scraper at `personas/scrapers/buffett.py` is kept as a reference template for the six macro scrapers (deferred follow-ups)
- Per-persona corpus: scrape primary sources → token-window chunker → Chroma collection (one per persona, persistent on disk) → auto-generated `PersonaCard` (belief summary, decision framework, signature phrases, voice notes)
- Per-turn chat: query embedded → top-k chunks → system prompt with profile card + chunks → `PersonaResponse` (text + cited_sources mapped back to `Citation` objects with snippet + score)
- Panel mode: parallel `asyncio.gather` across N personas (no peer visibility, preserves diversity) → synthesis pass returning `PanelSynthesis` (consensus, disagreements, strongest objection, recommended modifications)
- Conversations attach to `ApprovalItem.conversations[]`; panel discussions attach to `ApprovalItem.panel_discussions[]`. Full audit trail preserved with each approval
- New CLI: `castelino persona-build --persona buffett --full-name "Warren Buffett" --role "Value investor"`
- Dashboard: new `/approvals/:entryId/consult` route with three-column layout (pending-item summary + decision notes / persona picker + "Run Panel" button / chat thread); `Apply Synthesis` button copies the synthesis into the decision-notes field
- 5 new dashboard endpoints: list/send conversation messages, run panel, list personas, get persona
- Personas DO NOT participate in the agent pipeline — they're advisors, invoked only from the dashboard
- Standalone chat (free-form): each persona card on /personas now has a "Chat" button that opens a slide-over drawer with one rolling thread per persona, persisted to `data/personas/conversations/<id>.json`. 30-day sliding window for LLM context — older messages stay on disk and visible (faded) but don't pay tokens. Reuses `PersonaAgent.chat()` with empty `approval_payload`.
- Two new endpoints: `GET /personas/:id/thread`, `POST /personas/:id/thread/messages`
- Sonar fallback (`personas/sonar_fetcher.py`): when a primary scraper (RSS/YouTube/PDF) returns < 3 docs, Perplexity Sonar does web search with citations and returns 2-3 paragraph summaries of recent persona commentary. Cached 24h. Wired into Krugman/El-Erian/Summers scrapers (Project Syndicate global feed only has 20 most recent globally; per-columnist feeds don't exist).
- Design doc: `docs/plans/2026-05-08-persona-agents-design.md`
- Implementation plan: `docs/plans/2026-05-08-persona-agents-plan.md` (20 bite-sized TDD tasks across 9 waves)
- Standalone-chat design doc: `docs/plans/2026-05-08-persona-standalone-chat-design.md`

### 2026-05-08 — Fed Speech Listener (`SPEECH_DEVIATION` trigger source)
- New trigger source: streams live Fed speech audio through Deepgram STT, scores each sentence on a versioned hawkish/dovish lexicon, fires the pipeline when a 5-sentence rolling window deviates >1.5σ from the speaker's own 12-month rhetorical baseline
- Three layers under `src/castelino/triggers/speech/`: persona builder (offline scrape→score→time-weighted baseline), live listener (async STT events → SpeechSegment per sentence), deviation scorer (Stage A z-score + Stage B `gpt-4o-mini` confirmation gate)
- Persona-relative deviation is the signal — a dovish Powell turning hawkish carries far more information than a hawkish Powell staying hawkish
- Same `score_sentence()` used for both baseline construction and live scoring (load-bearing invariant; lexicon is versioned `hawkish_dovish_v1.yaml` and corpus rescored on bumps)
- Structural enforcement of hard rules: threshold check before LLM call, cooldown caps emissions at one per `event_id`
- New CLI commands: `castelino persona-refresh --speaker powell`, `castelino speech-test --transcript-file path --dry-run`
- Speakers and v2 sources extensible via `config.yaml::speech.speakers`; orchestrator graph unchanged (new `TriggerSource.SPEECH_DEVIATION` flows in at `current_event` like any other trigger)
- Design doc: `docs/plans/2026-05-07-fed-speech-listener-design.md`
- Implementation plan: `docs/plans/2026-05-07-fed-speech-listener-plan.md` (24 bite-sized TDD tasks across 8 waves)
