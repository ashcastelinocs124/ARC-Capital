# Technical Readiness Multiplier

**Date:** 2026-05-07
**Status:** Approved

## Problem

The significance scorer's materiality is LLM-guessed from headline text alone.
It has no sense of whether the market is primed for the headline's direction.
"German factory orders fall" scores the same whether SPY is overbought at RSI 72
with distribution underway (primed for a selloff catalyst) or sitting at RSI 50
mid-range (indifferent).

## Decision

Add a deterministic **readiness multiplier** (0.7–1.5) between pass 1 (LLM
scoring) and pass 2 (Polymarket/X enrichment). For each scored headline:

1. Map `asset_classes_affected` → representative instruments
2. Pull RSI(14), MACD histogram, OBV trend via yfinance (cached)
3. Compute a readiness multiplier based on alignment with headline direction
4. `adjusted_materiality = materiality × multiplier`, clamped [0.0, 1.0]

No LLM call — pure Python math on cached price data.

## Instrument Mapping

| Asset class tagged | Check technicals on |
|--------------------|---------------------|
| equity | SPY |
| bond_etf | TLT |
| fx | DXY (via UUP ETF) |
| commodity_etf | GLD |
| futures | CL_F (oil) |

If multiple asset classes are tagged, average the multipliers.

## Readiness Scoring

### RSI(14)
| Condition | Headline direction | Multiplier contribution |
|-----------|-------------------|------------------------|
| RSI > 70 (overbought) | bearish (growth down) | +0.20 |
| RSI > 70 (overbought) | bullish (growth up) | -0.10 (fighting the spring) |
| RSI < 30 (oversold) | bullish (growth up) | +0.20 |
| RSI < 30 (oversold) | bearish (growth down) | -0.10 |
| RSI 30–70 | any | 0.00 |

### MACD Histogram
| Condition | Headline direction | Multiplier contribution |
|-----------|-------------------|------------------------|
| MACD crossing below signal (bearish) | bearish | +0.10 |
| MACD crossing above signal (bullish) | bullish | +0.10 |
| MACD contradicts headline | any | -0.10 |
| MACD flat/neutral | any | 0.00 |

### OBV Trend (5-session slope)
| Condition | Headline direction | Multiplier contribution |
|-----------|-------------------|------------------------|
| OBV declining (distribution) | bearish | +0.10 |
| OBV rising (accumulation) | bullish | +0.10 |
| OBV contradicts headline | any | -0.10 |
| OBV flat | any | 0.00 |

### Final multiplier

```
readiness = 1.0 + rsi_adj + macd_adj + obv_adj
clamped to [0.7, 1.5]
```

Maximum boost: +0.5 (all three aligned + extreme RSI).
Maximum penalty: -0.3 (all three contradicting).

## Scoring Flow (updated)

```
Pass 1: score_batch()           ← LLM scores bare headlines
    │
    ▼
Technical readiness multiplier   ← NEW: deterministic, no LLM
    │   adjusted_materiality = materiality × readiness
    │
    ▼
Filter borderlines (0.4–0.8)
    │
    ▼
Pass 2: Polymarket + X enrichment  ← re-score borderlines
    │
    ▼
conv.append(final_scores)
```

## Files Touched

| File | Change |
|------|--------|
| `triggers/readiness.py` | **NEW** — technical readiness multiplier logic |
| `triggers/runner.py` | Wire readiness between pass 1 and borderline filter |

No config changes — the multiplier ranges and indicator parameters are
hardcoded constants (not tunable knobs for v1). Can be moved to config later
if we need to tune.
