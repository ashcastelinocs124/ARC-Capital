"""Trade detail HTML pages — one per executed trade.

Each card stitches together: trigger → world state → hypothesis → expression →
research bundle → bull/bear → verdict → guard → fill → outcome (closed P&L).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from jinja2 import Template

from castelino.config import get_settings
from castelino.memory import io as memio
from castelino.memory.schemas import (
    BearCase,
    BullCase,
    GuardDecision,
    Hypothesis,
    JournalEntry,
    ResearchBundle,
    TradeEvent,
    TradeExpression,
    Verdict,
)

CARD_TEMPLATE = Template(
    """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Trade — {{ trade.instrument }} ({{ trade.event_type }})</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 900px; margin: 32px auto; padding: 0 16px; color: #1f2328; }
  h1 { margin-bottom: 4px; }
  h2 { margin-top: 32px; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 12px;
          background: #ddf4ff; color: #0969da; font-size: 12px; margin-right: 4px; }
  .green { background: #dafbe1; color: #1a7f37; }
  .red { background: #ffebe9; color: #cf222e; }
  pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; }
  td, th { padding: 6px 10px; border-bottom: 1px solid #eaeef2; text-align: left; }
</style>
</head>
<body>
<h1>{{ trade.event_type|upper }} — {{ trade.instrument }}</h1>
<p>
  <span class="pill">{{ trade.event_type }}</span>
  <span class="pill {% if trade.pnl >= 0 %}green{% else %}red{% endif %}">
    P&L ${{ "{:,.2f}".format(trade.pnl) }}
  </span>
  <span class="pill">{{ trade.timestamp }}</span>
</p>

<h2>Hypothesis</h2>
{% if hypothesis %}
<p><strong>{{ hypothesis.thesis }}</strong></p>
<table>
<tr><th>Regime</th><td>{{ hypothesis.regime_value }}</td></tr>
<tr><th>Conviction</th><td>{{ hypothesis.conviction_value }}</td></tr>
<tr><th>Horizon</th><td>{{ hypothesis.horizon_days }}d</td></tr>
<tr><th>Kill criteria</th><td><ul>{% for kc in hypothesis.kill_criteria %}<li>{{ kc }}</li>{% endfor %}</ul></td></tr>
</table>
{% else %}<p><em>No parent hypothesis recorded.</em></p>{% endif %}

<h2>Expression</h2>
{% if expression %}
<table>
<tr><th>Direction</th><td>{{ expression.direction_value }}</td></tr>
<tr><th>Target size (% NAV)</th><td>{{ "{:.4f}".format(expression.target_size_pct_nav) }}</td></tr>
<tr><th>Initial stop (%)</th><td>{{ "{:.2f}".format(expression.initial_stop_pct * 100) }}%</td></tr>
<tr><th>Rationale</th><td>{{ expression.rationale }}</td></tr>
</table>
{% endif %}

<h2>Research bundle</h2>
{% if research %}
<table>
<tr><th>Web sentiment</th><td>{{ research.web_sentiment }} — {{ research.web_summary }}</td></tr>
<tr><th>TA</th><td>trend={{ research.trend }}, RSI={{ "{:.1f}".format(research.rsi) }} — {{ research.ta_interp }}</td></tr>
<tr><th>Backtest</th><td>hit_rate={{ "{:.2f}".format(research.hit_rate) }}, avg={{ "{:.2f}".format(research.avg_return) }}% — {{ research.bt_interp }}</td></tr>
<tr><th>Risk</th><td>vol60={{ "{:.3f}".format(research.vol60) }}, corr={{ "{:.2f}".format(research.corr) }} — {{ research.risk_interp }}</td></tr>
</table>
{% endif %}

<h2>Debate</h2>
{% if bull %}<p><strong>Bull ({{ bull.confidence }}):</strong> {{ bull.strongest }}</p>{% endif %}
{% if bear %}<p><strong>Bear ({{ bear.confidence }}):</strong> {{ bear.strongest }}</p>{% endif %}
{% if verdict %}
<p><strong>Verdict — {{ verdict.decision }}:</strong> {{ verdict.decisive_factor }}</p>
{% if verdict.dissent %}<p><em>Dissent:</em> {{ verdict.dissent }}</p>{% endif %}
{% endif %}

<h2>Guard</h2>
{% if guard %}
<p><strong>{{ guard.decision }}</strong> — {{ guard.rationale }}</p>
{% if guard.triggered_rules %}<p>Triggered: {{ guard.triggered_rules|join(', ') }}</p>{% endif %}
{% endif %}

<h2>Fill</h2>
<table>
<tr><th>Quantity</th><td>{{ trade.quantity }}</td></tr>
<tr><th>Fill price</th><td>{{ "{:.4f}".format(trade.fill_price) }}</td></tr>
<tr><th>Slippage cost</th><td>${{ "{:.2f}".format(trade.slippage_cost) }}</td></tr>
<tr><th>Commission</th><td>${{ "{:.2f}".format(trade.commission_cost) }}</td></tr>
<tr><th>Pre-NAV → Post-NAV</th><td>${{ "{:,.2f}".format(trade.pre_trade_nav) }} → ${{ "{:,.2f}".format(trade.post_trade_nav) }}</td></tr>
<tr><th>Notes</th><td>{{ trade.notes }}</td></tr>
</table>

</body>
</html>
"""
)


def _build_index() -> dict[str, list[JournalEntry]]:
    """Group entries by parent linkages so we can stitch a card from a TradeEvent up."""
    by_id: dict[str, JournalEntry] = {}
    by_parent_exp: dict[str, list[JournalEntry]] = defaultdict(list)
    for e in memio.read_short_term():
        by_id[e.entry_id] = e
        pid = getattr(e, "parent_expression_id", None)
        if pid:
            by_parent_exp[pid].append(e)
    return {"by_id": by_id, "by_parent_exp": by_parent_exp}


def generate() -> list[Path]:
    cfg = get_settings()
    out_dir = cfg.resolved_paths.reports / "trades"
    out_dir.mkdir(parents=True, exist_ok=True)

    idx = _build_index()
    by_id: dict[str, JournalEntry] = idx["by_id"]
    by_parent_exp: dict[str, list[JournalEntry]] = idx["by_parent_exp"]

    out: list[Path] = []
    for e in by_id.values():
        if not isinstance(e, TradeEvent):
            continue
        out.append(_render_card(e, by_id, by_parent_exp, out_dir))

    # Index page
    out.append(_write_index(by_id, out_dir.parent))
    return out


def _render_card(
    trade: TradeEvent,
    by_id: dict[str, JournalEntry],
    by_parent_exp: dict[str, list[JournalEntry]],
    out_dir: Path,
) -> Path:
    expression = None
    research = None
    bull = None
    bear = None
    verdict = None
    guard = None
    hypothesis = None

    if trade.parent_expression_id:
        expression = by_id.get(trade.parent_expression_id)
        sibs = by_parent_exp.get(trade.parent_expression_id, [])
        for s in sibs:
            if isinstance(s, ResearchBundle):
                research = s
            elif isinstance(s, BullCase):
                bull = s
            elif isinstance(s, BearCase):
                bear = s
            elif isinstance(s, Verdict):
                verdict = s
            elif isinstance(s, GuardDecision):
                guard = s

    if expression and isinstance(expression, TradeExpression):
        h = by_id.get(expression.parent_hypothesis_id)
        if isinstance(h, Hypothesis):
            hypothesis = h

    ctx = {
        "trade": {
            "instrument": trade.instrument_id,
            "event_type": trade.event_type,
            "pnl": trade.realized_pnl,
            "timestamp": trade.timestamp.isoformat(timespec="seconds"),
            "quantity": trade.quantity,
            "fill_price": trade.fill_price,
            "slippage_cost": trade.slippage_cost,
            "commission_cost": trade.commission_cost,
            "pre_trade_nav": trade.pre_trade_nav,
            "post_trade_nav": trade.post_trade_nav,
            "notes": trade.notes,
        },
        "hypothesis": (
            {
                "thesis": hypothesis.thesis,
                "regime_value": hypothesis.regime.value,
                "conviction_value": hypothesis.conviction.value,
                "horizon_days": hypothesis.horizon_days,
                "kill_criteria": [c.description for c in hypothesis.kill_criteria],
            }
            if hypothesis else None
        ),
        "expression": (
            {
                "direction_value": expression.direction.value,
                "target_size_pct_nav": expression.target_size_pct_nav,
                "initial_stop_pct": expression.initial_stop_pct,
                "rationale": expression.rationale,
            }
            if isinstance(expression, TradeExpression) else None
        ),
        "research": (
            {
                "web_sentiment": research.web.sentiment,
                "web_summary": research.web.summary,
                "trend": research.technical.trend,
                "rsi": research.technical.rsi_14,
                "ta_interp": research.technical.interpretation,
                "hit_rate": research.backtest.hit_rate,
                "avg_return": research.backtest.avg_return_pct,
                "bt_interp": research.backtest.interpretation,
                "vol60": research.risk.realized_vol_60d,
                "corr": research.risk.correlation_to_book,
                "risk_interp": research.risk.interpretation,
            }
            if research else None
        ),
        "bull": ({"confidence": bull.confidence.value, "strongest": bull.strongest_argument} if bull else None),
        "bear": ({"confidence": bear.confidence.value, "strongest": bear.strongest_argument} if bear else None),
        "verdict": ({"decision": verdict.decision, "decisive_factor": verdict.decisive_factor, "dissent": verdict.dissent} if verdict else None),
        "guard": ({"decision": guard.decision, "rationale": guard.rationale, "triggered_rules": guard.triggered_rules} if guard else None),
    }
    html = CARD_TEMPLATE.render(**ctx)
    p = out_dir / f"{trade.entry_id}.html"
    p.write_text(html, encoding="utf-8")
    return p


def _write_index(by_id: dict[str, JournalEntry], reports_dir: Path) -> Path:
    """Top-level index linking equity curve + every trade card."""
    items = []
    for e in by_id.values():
        if isinstance(e, TradeEvent):
            items.append((e.timestamp, e))
    items.sort(reverse=True)
    rows = "\n".join(
        f'<li><a href="trades/{e.entry_id}.html">{e.timestamp:%Y-%m-%d} '
        f'{e.event_type} {e.instrument_id} (P&L ${e.realized_pnl:+,.2f})</a></li>'
        for _, e in items
    )
    html = f"""\
<!doctype html>
<html><head><meta charset="utf-8"><title>Castelino Capital — Reports</title>
<style>body {{font-family:-apple-system,sans-serif;max-width:900px;margin:32px auto;padding:0 16px}}
img {{max-width:100%;border:1px solid #d0d7de;border-radius:6px}}</style></head>
<body>
<h1>Castelino Capital — Reports</h1>
<h2>Equity</h2>
<img src="equity_curve.png" alt="equity curve">
<img src="drawdown.png" alt="drawdown">
<h2>Exposure</h2>
<img src="exposure_by_class.png" alt="exposure by class">
<img src="exposure_by_instrument.png" alt="exposure by instrument">
<h2>Attribution</h2>
<img src="attribution_by_instrument.png" alt="attr by instrument">
<img src="attribution_by_hypothesis.png" alt="attr by hypothesis">
<h2>Trades</h2>
<ul>{rows or '<li>(none yet)</li>'}</ul>
</body></html>
"""
    p = reports_dir / "index.html"
    p.write_text(html)
    return p
