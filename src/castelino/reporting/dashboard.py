"""Live dashboard — single-page HTML view of the book.

Shows: NAV/cash/exposure metrics, open positions with live P&L, recent fills,
recent hypotheses + triggers, plus the existing PNG charts. Regenerated on
demand via `ckm dashboard` (or as a side-effect of `ckm report`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Template

from castelino.config import get_settings
from castelino.execution.portfolio import Portfolio
from castelino.execution.pricing import PricingError, latest
from castelino.memory import io as memio
from castelino.memory.schemas import (
    Hypothesis,
    PrincipleWarning,
    TradeEvent,
    TriggerRecord,
)

DASHBOARD = Template(
    r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Castelino Capital — Dashboard</title>
<meta http-equiv="refresh" content="60">
<style>
  :root {
    --bg: #0d1117;
    --panel: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --green: #3fb950;
    --red: #f85149;
    --blue: #58a6ff;
    --amber: #d29922;
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    margin: 0; padding: 24px; max-width: 1400px; margin: 0 auto;
  }
  header { display: flex; justify-content: space-between; align-items: baseline;
           border-bottom: 1px solid var(--border); padding-bottom: 12px; }
  h1 { margin: 0; font-size: 22px; font-weight: 600; }
  h2 { margin: 32px 0 12px; font-size: 14px; text-transform: uppercase;
       letter-spacing: 0.06em; color: var(--muted); font-weight: 600; }
  .stamp { color: var(--muted); font-size: 12px; }
  .grid { display: grid; gap: 12px; }
  .stats { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-top: 16px; }
  .stat {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px 16px;
  }
  .stat .label { font-size: 11px; text-transform: uppercase; color: var(--muted);
                 letter-spacing: 0.05em; }
  .stat .value { font-size: 22px; font-variant-numeric: tabular-nums; margin-top: 4px;
                 font-weight: 600; }
  .pos { color: var(--green); }
  .neg { color: var(--red); }
  .muted { color: var(--muted); }
  table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums;
          background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
          overflow: hidden; }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
  th { font-size: 11px; text-transform: uppercase; color: var(--muted);
       letter-spacing: 0.05em; font-weight: 600; background: rgba(255,255,255,0.02); }
  tr:last-child td { border-bottom: none; }
  td.num { text-align: right; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px;
          font-weight: 600; }
  .pill.long { background: rgba(63, 185, 80, 0.15); color: var(--green); }
  .pill.short { background: rgba(248, 81, 73, 0.15); color: var(--red); }
  .pill.proceed, .pill.approved, .pill.open { background: rgba(63,185,80,0.15); color: var(--green); }
  .pill.reject, .pill.hard_veto, .pill.close { background: rgba(248,81,73,0.15); color: var(--red); }
  .pill.modify, .pill.amended, .pill.soft_warning, .pill.trim, .pill.stop_loss
    { background: rgba(210,153,34,0.15); color: var(--amber); }
  .charts { display: grid; gap: 16px; grid-template-columns: 1fr 1fr; margin-top: 12px; }
  .charts img { width: 100%; border: 1px solid var(--border); border-radius: 8px;
                background: white; }
  a { color: var(--blue); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .empty { color: var(--muted); padding: 20px; text-align: center; }
  .footer { color: var(--muted); font-size: 12px; margin-top: 40px; padding-top: 12px;
            border-top: 1px solid var(--border); }
</style>
</head>
<body>
<header>
  <h1>Castelino Capital — Dashboard</h1>
  <span class="stamp">refreshed {{ asof }} · auto-reloads every 60s</span>
</header>

<div class="grid stats">
  <div class="stat"><div class="label">NAV</div>
    <div class="value {{ nav_class }}">${{ "{:,.0f}".format(nav) }}</div>
    <div class="stamp">{{ ret_pct }}% from initial</div></div>
  <div class="stat"><div class="label">Cash</div>
    <div class="value">${{ "{:,.0f}".format(cash) }}</div>
    <div class="stamp">{{ cash_pct }}% of NAV</div></div>
  <div class="stat"><div class="label">Gross exposure</div>
    <div class="value">${{ "{:,.0f}".format(gross) }}</div>
    <div class="stamp">{{ gross_pct }}% of NAV</div></div>
  <div class="stat"><div class="label">Net exposure</div>
    <div class="value">${{ "{:,.0f}".format(net) }}</div>
    <div class="stamp">{{ net_pct }}% of NAV</div></div>
  <div class="stat"><div class="label">Unrealized P&L</div>
    <div class="value {{ unrealized_class }}">{{ unrealized_str }}</div>
    <div class="stamp">{{ n_pos }} open positions</div></div>
  <div class="stat"><div class="label">Realized P&L (cum)</div>
    <div class="value {{ realized_class }}">{{ realized_str }}</div>
    <div class="stamp">{{ n_closed }} closed trades</div></div>
</div>

<h2>Open positions</h2>
{% if positions %}
<table>
  <thead><tr>
    <th>Instrument</th><th>Side</th><th>Class</th>
    <th class="num">Qty</th><th class="num">Entry</th><th class="num">Mark</th>
    <th class="num">Mkt value</th><th class="num">% NAV</th>
    <th class="num">Unrealized $</th><th class="num">Unrealized %</th>
    <th>Stop</th><th>Hypothesis</th>
  </tr></thead>
  <tbody>
  {% for p in positions %}
  <tr>
    <td><strong>{{ p.instrument_id }}</strong></td>
    <td><span class="pill {{ 'long' if p.qty > 0 else 'short' }}">{{ 'LONG' if p.qty > 0 else 'SHORT' }}</span></td>
    <td class="muted">{{ p.asset_class }}</td>
    <td class="num">{{ "{:,.4f}".format(p.qty) }}</td>
    <td class="num">{{ "{:,.4f}".format(p.entry) }}</td>
    <td class="num">{{ "{:,.4f}".format(p.mark) }}</td>
    <td class="num">${{ "{:,.0f}".format(p.mv) }}</td>
    <td class="num muted">{{ "{:.2f}".format(p.pct_nav) }}%</td>
    <td class="num {{ p.cls }}">${{ "{:+,.2f}".format(p.unrealized) }}</td>
    <td class="num {{ p.cls }}">{{ "{:+.2f}".format(p.unrealized_pct) }}%</td>
    <td class="muted">{{ p.stop }}</td>
    <td class="muted">{{ p.parent_hyp }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}<div class="empty">No open positions.</div>{% endif %}

<h2>Recent fills</h2>
{% if fills %}
<table>
  <thead><tr>
    <th>When</th><th>Type</th><th>Instrument</th>
    <th class="num">Qty</th><th class="num">Fill price</th>
    <th class="num">Slippage</th><th class="num">Commission</th>
    <th class="num">Realized P&L</th><th>Notes</th>
  </tr></thead>
  <tbody>
  {% for f in fills %}
  <tr>
    <td class="muted">{{ f.when }}</td>
    <td><span class="pill {{ f.event_type }}">{{ f.event_type|upper }}</span></td>
    <td><a href="trades/{{ f.entry_id }}.html"><strong>{{ f.instrument_id }}</strong></a></td>
    <td class="num">{{ "{:+,.4f}".format(f.qty) }}</td>
    <td class="num">{{ "{:,.4f}".format(f.fill_price) }}</td>
    <td class="num muted">${{ "{:,.2f}".format(f.slippage) }}</td>
    <td class="num muted">${{ "{:,.2f}".format(f.commission) }}</td>
    <td class="num {{ f.cls }}">{{ "${:+,.2f}".format(f.realized) if f.realized != 0 else "—" }}</td>
    <td class="muted">{{ f.notes[:80] }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}<div class="empty">No fills yet.</div>{% endif %}

<h2>Recent hypotheses</h2>
{% if hypotheses %}
<table>
  <thead><tr>
    <th>When</th><th>Regime</th><th>Conv</th><th>Horizon</th>
    <th>Thesis</th><th>Kill criteria</th>
  </tr></thead>
  <tbody>
  {% for h in hypotheses %}
  <tr>
    <td class="muted">{{ h.when }}</td>
    <td><span class="pill">{{ h.regime }}</span></td>
    <td>{{ h.conviction }}</td>
    <td class="muted">{{ h.horizon }}d</td>
    <td>{{ h.thesis }}</td>
    <td class="muted">{{ h.kill }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}<div class="empty">No hypotheses yet — run <code>ckm run "&lt;headline&gt;"</code>.</div>{% endif %}

<h2>Recent triggers</h2>
{% if triggers %}
<table>
  <thead><tr>
    <th>When</th><th>Source</th><th class="num">Sig</th><th>Headline</th>
  </tr></thead>
  <tbody>
  {% for t in triggers %}
  <tr>
    <td class="muted">{{ t.when }}</td>
    <td class="muted">{{ t.source }}</td>
    <td class="num"><strong>{{ "{:.2f}".format(t.sig) }}</strong></td>
    <td>{{ t.headline }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}<div class="empty">No triggers in journal.</div>{% endif %}

{% if warnings %}
<h2>Recent principle warnings</h2>
<table>
  <thead><tr><th>When</th><th>Rule</th><th>Severity</th><th>Description</th></tr></thead>
  <tbody>
  {% for w in warnings %}
  <tr>
    <td class="muted">{{ w.when }}</td>
    <td><strong>{{ w.rule_id }}</strong></td>
    <td><span class="pill {{ 'hard_veto' if w.severity == 'hard' else 'modify' }}">{{ w.severity|upper }}</span></td>
    <td>{{ w.description }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}

<h2>Charts</h2>
<div class="charts">
  <img src="equity_curve.png" alt="equity curve">
  <img src="drawdown.png" alt="drawdown">
  <img src="exposure_by_class.png" alt="exposure by class">
  <img src="exposure_by_instrument.png" alt="exposure by instrument">
  <img src="attribution_by_instrument.png" alt="attribution by instrument">
  <img src="attribution_by_hypothesis.png" alt="attribution by hypothesis">
</div>

<div class="footer">
  Castelino Capital — multi-agent macro fund · {{ counts_str }}
</div>
</body>
</html>
"""
)


def _live_mark(instrument_id: str, fallback: float) -> float:
    """Try to mark to the latest live price; fall back to last known on outage."""
    try:
        return latest(instrument_id).price
    except PricingError:
        return fallback


def _fmt_position(p, nav: float, refresh_marks: bool) -> dict:
    mark = _live_mark(p.instrument_id, p.current_price) if refresh_marks else p.current_price
    mv = p.quantity * mark  # multiplier already 1.0 except futures; keep simple display
    cost = p.quantity * p.avg_entry_price
    unrealized = mv - cost
    cls = "pos" if unrealized >= 0 else "neg"
    return {
        "instrument_id": p.instrument_id,
        "qty": p.quantity,
        "entry": p.avg_entry_price,
        "mark": mark,
        "mv": mv,
        "pct_nav": (abs(mv) / nav * 100) if nav > 0 else 0.0,
        "unrealized": unrealized,
        "unrealized_pct": ((mark / p.avg_entry_price - 1) * 100) if p.avg_entry_price > 0
                         else 0.0,
        "cls": cls,
        "asset_class": getattr(p.asset_class, "value", str(p.asset_class)),
        "stop": f"{p.stop_loss:.4f}" if p.stop_loss else "—",
        "parent_hyp": (p.parent_hypothesis_id or "—")[:14],
    }


def generate(refresh_marks: bool = True) -> Path:
    """Render the dashboard and return its path. If `refresh_marks=True`,
    re-prices every position via the live `pricing.latest()` adapter; if False,
    uses the last `current_price` stored in `portfolio.json` (no network)."""
    cfg = get_settings()
    out_dir = cfg.resolved_paths.reports
    out_dir.mkdir(parents=True, exist_ok=True)

    pf = Portfolio.load()
    nav = pf.nav
    initial = pf.initial_nav

    positions_ctx = [_fmt_position(p, nav, refresh_marks) for p in pf.positions]

    # Pull recent journal entries
    entries = memio.read_short_term()
    by_kind = {kind: 0 for kind in (
        "TriggerRecord", "Hypothesis", "Verdict", "GuardDecision",
        "TradeEvent", "PrincipleWarning",
    )}
    for e in entries:
        by_kind[e.kind] = by_kind.get(e.kind, 0) + 1

    fills_ctx = []
    for e in sorted(
        [e for e in entries if isinstance(e, TradeEvent)],
        key=lambda x: x.timestamp, reverse=True,
    )[:15]:
        cls = "pos" if e.realized_pnl > 0 else ("neg" if e.realized_pnl < 0 else "muted")
        fills_ctx.append({
            "when": e.timestamp.strftime("%Y-%m-%d %H:%M"),
            "event_type": e.event_type,
            "instrument_id": e.instrument_id,
            "entry_id": e.entry_id,
            "qty": e.quantity,
            "fill_price": e.fill_price,
            "slippage": e.slippage_cost,
            "commission": e.commission_cost,
            "realized": e.realized_pnl,
            "cls": cls,
            "notes": e.notes or "",
        })

    hypotheses_ctx = []
    for h in sorted(
        [e for e in entries if isinstance(e, Hypothesis)],
        key=lambda x: x.timestamp, reverse=True,
    )[:5]:
        hypotheses_ctx.append({
            "when": h.timestamp.strftime("%Y-%m-%d %H:%M"),
            "regime": h.regime.value,
            "conviction": h.conviction.value,
            "horizon": h.horizon_days,
            "thesis": h.thesis,
            "kill": " | ".join(c.description for c in h.kill_criteria)[:200],
        })

    triggers_ctx = []
    for t in sorted(
        [e for e in entries if isinstance(e, TriggerRecord)],
        key=lambda x: x.timestamp, reverse=True,
    )[:8]:
        triggers_ctx.append({
            "when": t.timestamp.strftime("%Y-%m-%d %H:%M"),
            "source": t.source.value,
            "sig": t.significance,
            "headline": t.headline,
        })

    warnings_ctx = []
    for w in sorted(
        [e for e in entries if isinstance(e, PrincipleWarning)],
        key=lambda x: x.timestamp, reverse=True,
    )[:6]:
        warnings_ctx.append({
            "when": w.timestamp.strftime("%Y-%m-%d %H:%M"),
            "rule_id": w.rule_id,
            "severity": w.severity,
            "description": w.description,
        })

    n_closed = sum(
        1 for e in entries
        if isinstance(e, TradeEvent) and e.event_type in ("close", "stop_loss")
    )

    ret_pct = (nav / initial - 1) * 100 if initial > 0 else 0.0
    unrealized = pf.unrealized_pnl
    realized = pf.realized_pnl

    counts_str = "  ·  ".join(f"{k}: {v}" for k, v in by_kind.items() if v)

    html = DASHBOARD.render(
        asof=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        nav=nav, cash=pf.cash, gross=pf.gross_exposure, net=pf.net_exposure,
        nav_class="pos" if nav >= initial else "neg",
        ret_pct=f"{ret_pct:+.2f}",
        cash_pct=f"{pf.cash / nav * 100:.1f}" if nav > 0 else "0.0",
        gross_pct=f"{pf.gross_exposure / nav * 100:.1f}" if nav > 0 else "0.0",
        net_pct=f"{pf.net_exposure / nav * 100:.1f}" if nav > 0 else "0.0",
        unrealized_str=f"${unrealized:+,.2f}",
        unrealized_class="pos" if unrealized >= 0 else "neg",
        realized_str=f"${realized:+,.2f}",
        realized_class="pos" if realized >= 0 else "neg",
        n_pos=len(pf.positions), n_closed=n_closed,
        positions=positions_ctx, fills=fills_ctx,
        hypotheses=hypotheses_ctx, triggers=triggers_ctx, warnings=warnings_ctx,
        counts_str=counts_str or "(empty journal)",
    )

    p = out_dir / "dashboard.html"
    p.write_text(html)
    return p
