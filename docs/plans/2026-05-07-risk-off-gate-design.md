# Risk-Off Forward Classifier + Trading Gate

**Date:** 2026-05-07
**Status:** Approved

## Problem

The 4-quadrant regime nowcaster (growth × inflation) tells us *which* macro
playbook to run, but doesn't measure *fragility*. A Reflation regime with
calm credit and tight spreads is very different from Reflation with HY OAS
blowing out and VIX rising. The pipeline currently treats them the same.

## Decision

Add a **separate forward-classifier** that predicts P(SPY drawdown >5% next
month) using credit + vol + dollar features. This probability feeds a
**trading gate** that sits between the Constitutional Guard and the Portfolio
Agent. The gate translates probability into a size multiplier per trade.

This is a **defensive overlay**, not a regime change. The regime nowcaster
still picks the playbook. The gate only ever shrinks, blocks, or — at extremes
— amplifies risk-on positions.

## Classifier

### Features

| Indicator | Source | Captures |
|-----------|--------|----------|
| BAMLH0A0HYM2 | FRED | HY OAS — credit stress |
| BAMLC0A0CM | FRED | IG OAS — early-warning credit |
| VIXCLS | FRED | Implied equity vol |
| ^MOVE | yfinance | Treasury vol (often leads equity vol) |
| DTWEXBGS | FRED | Trade-weighted USD — global liquidity |
| HYG/IEF | yfinance | Risky vs safe bond ETF ratio |

Each feature contributes lag-1, lag-2, lag-3 columns. Monthly aggregation.

### Label

For each month-end `t`:
```python
window = SPY[t : t + 30 days]
peak = window.expanding().max()
drawdown = (window / peak - 1).min()
label = 1 if drawdown < -0.05 else 0
```

### Training

- XGBoost binary classifier, same defaults as regime nowcaster
- `TimeSeriesSplit(n_splits=5)` walk-forward CV
- `scale_pos_weight` for class imbalance (~70-80 positive samples in 25y)
- Final model trained on all history, predicts current month

### Output

`data/risk_off_forecast.json`:
```json
{
  "prob_risk_off": 0.68,
  "as_of": "2026-05-07T14:00:00Z",
  "feature_month": "2026-04",
  "target_month": "2026-05",
  "model_version": "v1"
}
```

CLI: `castelino forecast-risk` (regenerates the JSON; run daily).

## Gate

### Tier policy

| `prob_risk_off` | Tier | Risk-on trade | Defensive trade |
|----------------|------|--------------|-----------------|
| `< 0.3` | calm | pass (1.0x) | pass (1.0x) |
| `0.3 – 0.6` | caution | downsize (0.5x) | pass (1.0x) |
| `0.6 – 0.85` | danger | veto (0.0x) | pass (1.0x) |
| `≥ 0.85` | capitulation | **amplify (1.3x)** | pass (1.0x) |

The capitulation tier captures the "buy fear at extremes" insight — when
prob_risk_off exceeds 0.85, historical forward returns are best, and the
gate flips from defensive to contrarian.

### Risk-on vs defensive classification

New field on `Instrument`: `risk_on: bool = True`.

Defensives (`risk_on=False`):
- Long-duration Treasuries: TLT, IEF, SHY
- IG credit: LQD
- Gold: GLD, GC_F
- Healthcare equity: XLV
- Yield context (non-tradable): DGS2, DGS10

Everything else stays risk-on by default. New instruments default to True.

### Output

```python
@dataclass
class GateDecision:
    action: Literal["pass", "downsize", "veto", "amplify"]
    size_multiplier: float
    prob_risk_off: float
    rationale: str
```

### Pipeline placement

```
GUARD (constitutional) ──► RISK-OFF GATE ──► PORTFOLIO AGENT
                                │
                                └── reads data/risk_off_forecast.json
```

Final sizing:
```
final_size = target × verdict_mult × guard_mult × gate.size_multiplier
```

If `gate.size_multiplier == 0.0`, no order is generated (effective veto).

### Configurability

```yaml
risk_gate:
  caution_min: 0.3
  caution_size_mult: 0.5
  danger_min: 0.6
  capitulation_min: 0.85
  capitulation_amplify: 1.3
```

## Files Touched

| File | Change |
|------|--------|
| `forecast/risk_off.py` | **NEW** — XGBoost classifier |
| `triggers/risk_gate.py` | **NEW** — tier logic, GateDecision |
| `data/instruments.py` | Add `risk_on` field; mark defensives False |
| `orchestrator/graph.py` | Insert `_node_risk_gate` between guard and portfolio |
| `orchestrator/state.py` | Add `gate_decisions: list[GateDecision]` |
| `agents/portfolio.py` | Multiply `gate.size_multiplier` into final size |
| `orchestrator/cli.py` | `castelino forecast-risk` command |
| `config.py` | Add `RiskGateCfg` model |
| `config.yaml` | Add `risk_gate:` section |

No agent prompt changes — gate is deterministic, no LLM call.
