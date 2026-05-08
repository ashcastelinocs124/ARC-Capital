# Trigger Redesign — Directional Conviction Ledger

**Date:** 2026-05-07
**Status:** Approved

## Problem

The current trigger system fires the pipeline only when a single headline
scores ≥ 0.7 on materiality. These high-impact events (FOMC, CPI, NFP) are
priced in within milliseconds — our 15-minute poll + multi-LLM pipeline is
structurally 15-60 minutes late on exactly the events we're tuned for.

Meanwhile, medium-significance headlines (0.4-0.7) get logged but never acted
on. A series of 0.5-0.6 headlines all pointing to Eurozone weakness is a
coherent, actionable macro signal — but the current design drops it.

## Decision

Replace the single-event threshold with a **Directional Conviction Ledger** —
a persistent, decaying accumulator that tracks headline conviction per macro
dimension (growth up/down, inflation up/down). Three parallel trigger paths
replace the single threshold:

1. **Black swan override** — single headline ≥ 0.9 fires instantly
2. **Regime shift** — XGBoost nowcaster label flips (runs daily)
3. **Accumulated conviction** — decayed directional sum crosses threshold

Plus the existing **cron fallback** (24h no-fire safety net).

### Alternatives rejected

- **Simple (non-directional) conviction ledger:** Treats all headlines equally.
  Five headlines about different topics sum the same as five about a building
  crisis. Can't distinguish coherent signal from noise.
- **Full Bayesian regime tracker:** Headlines update a posterior on regime
  probabilities. Most principled, but overkill for v1 — hard to tune, hard to
  explain, and the "approximate Bayesian" step would be an LLM call anyway.

## Significance Scorer Changes

Extend `HeadlineScore` with two new fields:

```python
class HeadlineScore(BaseModel):
    headline_id: str
    title: str
    materiality: float                                    # 0.0-1.0 (unchanged)
    asset_classes_affected: list[str]
    one_sentence_reason: str
    growth_direction: Literal["up", "down", "neutral"]    # NEW
    inflation_direction: Literal["up", "down", "neutral"] # NEW
```

The scorer prompt adds: classify whether each headline pushes growth
expectations up/down/neutral and inflation expectations up/down/neutral.
Headlines neutral on both dimensions contribute materiality but don't move
the directional ledger.

## Conviction Ledger

### Storage

Persistent file `data/conviction_ledger.json`:

```json
{
  "entries": [
    {
      "headline_id": "abc123",
      "title": "German factory orders fall 2.1%",
      "materiality": 0.55,
      "growth_direction": "down",
      "inflation_direction": "neutral",
      "timestamp": "2026-05-07T14:30:00Z"
    }
  ],
  "last_computed": "2026-05-07T14:45:00Z"
}
```

### Computation

Every 15-minute tick:

1. Score new headlines (existing LLM call, extended schema)
2. Append all scores ≥ 0.3 to the ledger (below 0.3 is noise)
3. Compute four decayed sums (half-life configurable, default 12h):

```
growth_bullish    = Σ (materiality × 2^(-age_h / 12))  where growth == "up"
growth_bearish    = Σ (materiality × 2^(-age_h / 12))  where growth == "down"
inflation_bullish = Σ (materiality × 2^(-age_h / 12))  where inflation == "up"
inflation_bearish = Σ (materiality × 2^(-age_h / 12))  where inflation == "down"
```

4. Prune entries older than 72h (3× half-life, contribute <0.01)

This is deterministic math — no LLM calls.

## Trigger Paths

Priority order in `tick()`:

### Path 1 — Black swan override (instant)
- Condition: any single headline with materiality ≥ 0.9
- Fires immediately, bypasses cooldown
- `TriggerSource.NEWS`, `raw_event_data.trigger_path = "black_swan"`

### Path 2 — Regime shift
- Condition: nowcaster regime label changes (runs daily after FRED update)
- Bypasses cooldown
- `TriggerSource.REGIME_SHIFT` (new enum value)
- Carries old/new regime + probabilities in `raw_event_data`

### Path 3 — Accumulated conviction
- Condition (either):
  - Any single dimension decayed sum ≥ `fire_threshold` (default 2.5)
  - Spread |bullish - bearish| on any dimension ≥ `spread_threshold` (default 2.0)
- Subject to cooldown (default 4h between conviction fires)
- `TriggerSource.CONVICTION` (new enum value)
- Carries all four sums + `contributing_headlines` in `raw_event_data`
- Contributing headlines get Sonar deep-reads before entering the pipeline

### Path 4 — Cron fallback (unchanged)
- Condition: nothing has fired for 24h
- `TriggerSource.CRON_FALLBACK`

### Threshold intuition

`fire_threshold = 2.5` means roughly:
- Five 0.5-materiality headlines in the same direction within one half-life
- Or three 0.6s and a 0.5
- Or two 0.7s and a few 0.4s

This is the "Eurozone is slowly falling apart" trigger.

## Configuration

```yaml
conviction:
  half_life_hours: 12
  fire_threshold: 2.5
  spread_threshold: 2.0
  cooldown_hours: 4
  black_swan_min: 0.9
  ledger_ttl_hours: 72
```

The old `news_significance_min: 0.7` becomes irrelevant for firing. Kept
temporarily for backward compat but no longer checked in the trigger path.
`news_log_min: 0.4` becomes the floor for ledger entry (renamed conceptually
but same config key for now).

## Files Touched

| File | Change |
|------|--------|
| `triggers/significance.py` | Add `growth_direction`, `inflation_direction` to scorer |
| `triggers/conviction.py` | **NEW** — ledger I/O, decay math, threshold checks |
| `triggers/runner.py` | Rewrite `tick()` with 4 trigger paths + cooldown |
| `memory/schemas.py` | Add `REGIME_SHIFT`, `CONVICTION` to `TriggerSource` |
| `config.py` | Add `ConvictionCfg` model |
| `config.yaml` | Add `conviction:` section |

No agent code changes — the trigger redesign is entirely in the trigger layer.
Agents see richer `TriggerRecord.raw_event_data` but the schema already
supports arbitrary dicts.
