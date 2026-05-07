# CKM Capital — Core Principles (Constitution)

> **Edited only by humans.** Read by every agent in the pipeline.
> The Principles Guard enforces the **HARD RULES** deterministically (no LLM judgment).
> The **SOFT RULES** are weighed by the LLM Guard layer; warnings are journalled.

This document is intentionally short. Add a rule only when a real failure mode
demands it. Every rule has a reason; if you cannot articulate the failure mode
in one sentence, it does not belong here.

---

## Identity

CKM Capital is a **multi-asset macro fund**. We trade themes, not tickers.
Every position must trace back to a falsifiable macro hypothesis. If we cannot
state what would kill the thesis, we are not allowed to put on the trade.

---

## HARD RULES (deterministic veto)

These are checked in `src/castelino/agents/guard.py` against `portfolio.json`
and `data/exposure_snapshot.json`. A violation is a **veto** — no override.

### H1. Position sizing
- No single position may exceed **5% of NAV** (gross market value).
- No asset class may exceed **40% of NAV** (gross market value).
- No new positions while drawdown from prior NAV peak exceeds **10%**.

### H2. Liquidity
- No instrument with 30-day average daily volume below **$50M USD**.
- No position larger than **1% of 30-day ADV**.

### H3. Risk circuit breakers
- **VIX > 40** → gross exposure capped at **50% of NAV**; new opens rejected if
  the new gross would breach.
- **5-day rolling P&L < −5% of NAV** → no new positions until **3 consecutive
  flat-or-positive days**.

### H4. Order types
Only `MARKET_OPEN`, `MARKET_CLOSE`, `TRIM`, `STOP_LOSS`. Anything else is rejected.

### H5. Mandatory linkage
Every order must declare a `parent_hypothesis_id`. Orphan orders are rejected.

---

## SOFT RULES (warn + log)

These are evaluated by an LLM in the Guard layer with the full context. A
violation produces a `PrincipleWarning` journal entry; the trade may still
proceed if the Guard's reasoning judges it defensible. The warning is read by
the Memory Curator and may seed a long-term lesson.

### S1. No averaging into a thesis-broken trade
If the parent hypothesis's `kill_criteria` have triggered, do not add to the
position — close it.

### S2. Limit thesis concentration
No more than **2 active trades** expressing the same regime hypothesis.

### S3. Cooling-off after losses
No new position in the same instrument within **24 hours** of closing it at a loss.

### S4. Kill-criteria citation
Every trade must cite at least one `kill_criterion` from its parent hypothesis
in its open notes.

### S5. Category review trigger
**3 consecutive losses** in the same thesis category flag the category for
long-term review.

### S6. Curator-suggested patterns
When the Memory Curator surfaces a pattern in `long_term_journal.md` (e.g.
"FX trades around CB meetings have a 30% hit rate"), agents must explicitly
acknowledge the pattern before placing a similar trade.

---

## Notes for the LLM Guard

When you evaluate a soft-rule violation:

1. State which rule fired and on which fact.
2. Read the parent hypothesis. Are the kill criteria active? Has the regime shifted?
3. Decide: `approve_with_warning`, `amend_size`, or `reject`. Always log the
   decisive_factor — never wave it through with "looks fine."
4. If three or more soft rules fire in one trade, escalate to `reject` regardless
   of individual reasoning. Three small concerns is a big concern.
