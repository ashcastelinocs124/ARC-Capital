# Sonar Deep-Read — Enriching the Input Layer

**Date:** 2026-05-07
**Status:** Approved

## Problem

The Current Event Agent receives only bare RSS headline titles (`list[str]`,
~5-50 words total). The entire downstream pipeline — hypothesis, debate,
portfolio — reasons from a 4-sentence summary of those titles. No full article
text, central-bank statements, or earnings transcripts ever enter the graph.

## Decision

Use Perplexity Sonar (search-grounded LLM) to fetch 150-200 word summaries
of significant headlines *after* significance scoring but *before* the pipeline
fires. Only headlines that pass the significance threshold (≥ 0.7) get enriched —
typically 1-3 per pipeline fire.

### Approach chosen: B — Enrich post-scoring

- Enrichment happens in `triggers/runner.py` between `score_batch()` and
  `fire_pipeline()`.
- Only pays for Sonar calls on headlines that actually matter.
- Keeps the data layer (RSS fetch) and agent layer (Current Event Agent) clean.

### Alternatives rejected

- **A — Enrich all at news layer:** Wasteful — enriches 20-30 headlines when
  only 1-3 matter.
- **C — Enrich inside Current Event node:** Mixes data-fetching with agent
  orchestration, harder to test/cache independently.

## Data Model Changes

### `NewsHeadline` (triggers/news.py)
New optional field: `deep_summary: str = ""` — Sonar-enriched summary.

### `WorldStateBrief` (memory/schemas.py)
New optional field: `source_summaries: list[str] = []` — 1:1 with `headlines`,
carrying the Sonar deep-read for each. Backward-compatible default.

## Enrichment Function

`enrich_significant_headlines()` in `triggers/news.py`:
- Takes headlines that passed significance scoring
- Calls Sonar for each: "Summarize this news event in 150-200 words with macro
  implications"
- Caches per headline ID in `data/cache/sonar_articles/`
- Falls back to RSS `summary` field if Sonar fails
- No-ops if `PERPLEXITY_API_KEY` is unset

## Pipeline Wiring

1. `runner.py` calls `enrich_significant_headlines()` after scoring, before
   `fire_pipeline()`
2. `fire_pipeline()` passes enriched headline data (titles + deep summaries)
3. `FundState` carries `source_summaries` to `_node_current_event`
4. Current Event Agent's `user_prompt` renders titles paired with context blocks
5. `WorldStateBrief.source_summaries` flows to hypothesis and research agents

## Files Touched

| File | Change |
|------|--------|
| `triggers/news.py` | Add `deep_summary` field, `enrich_significant_headlines()` |
| `memory/schemas.py` | Add `source_summaries` to `WorldStateBrief` |
| `triggers/runner.py` | Call enrichment post-scoring, pass enriched data |
| `agents/current_event.py` | Render titles + deep summaries in user prompt |
| `orchestrator/state.py` | Carry `source_summaries` through `FundState` |
