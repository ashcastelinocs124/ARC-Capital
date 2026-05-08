# Significance Enrichment — Polymarket + X Sentiment

**Date:** 2026-05-07
**Status:** Approved

## Problem

The significance scorer only sees bare headline titles (~10 words). It guesses
materiality from the words alone. Borderline headlines (0.4-0.8) are where the
score matters most — they're the ones that could shift the conviction ledger
toward or away from a fire — but the LLM has no market context to judge whether
the headline actually matters.

## Decision

Two-pass scoring: first pass scores headlines as today (bare titles). Second
pass re-scores only borderlines (0.4-0.8) with supplementary context from
Polymarket prediction markets and X/Twitter sentiment (via Sonar). The LLM
re-evaluates with richer information — same schema, same output.

### Alternatives rejected

- **Numeric adjustment (no second LLM call):** Deterministic score bumps
  (+0.15 for Polymarket price move, etc.). Blunt — can't adjust direction or
  reason about *why* the market moved.
- **Separate enrichment agent:** New agent producing structured MarketContext.
  Clean separation but overkill — this is just "add more text to the prompt."

## Polymarket Integration

New module `triggers/polymarket.py`.

**Data source:** Polymarket CLOB API (public, no auth required).

**Function:** `fetch_related_contracts(headline: str) -> list[ContractContext]`

1. Extract 2-3 macro keywords from headline
2. Search Polymarket's market endpoint for matching contracts
3. Return up to 3 matches with:
   - `question` — the contract question
   - `price` — current implied probability
   - `price_24h_ago` — yesterday's price
   - `volume_24h_usd` — 24h volume

Cached per headline ID for 1 hour.

## X/Twitter Sentiment via Sonar

Reuses existing Sonar client. New function in `triggers/news.py`:

`fetch_x_sentiment(headline: str) -> str`

Prompt: "What is the financial community on X/Twitter saying about this
headline? Report sentiment, engagement level, and contrarian takes in 2-3
sentences."

Returns raw text (~50-80 words). Cached per headline ID for 1 hour.
Falls back to empty string if Sonar unavailable.

## Two-Pass Scoring Flow

```
tick()
  ├─ score_batch(headlines)              ← Pass 1: bare titles
  ├─ filter borderlines (0.4 ≤ m ≤ 0.8)
  ├─ for each borderline:
  │    ├─ fetch_related_contracts()
  │    └─ fetch_x_sentiment()
  └─ rescore_borderlines()               ← Pass 2: enriched prompt
       overwrites first-pass scores
```

Second-pass prompt includes:
- Original headline + first-pass scores
- Polymarket contracts (question, price, 24h change, volume)
- X/Twitter sentiment summary

Scoring rules in prompt:
- Large prediction market move (>10pp) with volume = strong confirmation
- High X engagement from macro accounts = broader awareness
- Both confirm → score UP
- Market shows no reaction → score DOWN
- Adjust growth/inflation direction if context clarifies implications

## Configuration

```yaml
enrichment:
  borderline_min: 0.4
  borderline_max: 0.8
  polymarket_enabled: true
  x_sentiment_enabled: true
  cache_ttl_minutes: 60
```

## Fallback Chain

- Polymarket down → re-score with X context only
- Sonar down → re-score with Polymarket context only
- Both down → skip re-score, keep first-pass scores

## Files Touched

| File | Change |
|------|--------|
| `triggers/polymarket.py` | **NEW** — contract search, ContractContext |
| `triggers/significance.py` | Add `rescore_borderlines()` with enriched prompt |
| `triggers/news.py` | Add `fetch_x_sentiment()` via Sonar |
| `triggers/runner.py` | Wire two-pass flow into tick() |
| `config.py` | Add `EnrichmentCfg` model |
| `config.yaml` | Add `enrichment:` section |

No agent code changes. Entirely within the trigger/scoring layer.
