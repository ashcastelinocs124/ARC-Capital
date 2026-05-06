from __future__ import annotations
from fastapi import APIRouter
from castelino.execution.portfolio import Portfolio
from castelino.execution.pricing import PricingError, latest
from castelino.memory import io as memio
from castelino.memory.schemas import TradeEvent

router = APIRouter()


@router.get("/portfolio_metrics")
def portfolio_metrics():
    pf = Portfolio.load()
    nav = pf.nav
    initial = pf.initial_nav
    ret_pct = (nav / initial - 1) * 100 if initial > 0 else 0.0
    return [
        {"label": "NAV", "value": f"${nav:,.0f}", "delta": f"{ret_pct:+.2f}%"},
        {"label": "Cash", "value": f"${pf.cash:,.0f}", "subvalue": f"{pf.cash/nav*100:.1f}% of NAV" if nav > 0 else ""},
        {"label": "Gross Exposure", "value": f"${pf.gross_exposure:,.0f}"},
        {"label": "Net Exposure", "value": f"${pf.net_exposure:,.0f}"},
        {"label": "Unrealized P&L", "value": f"${pf.unrealized_pnl:+,.2f}"},
        {"label": "Positions", "value": str(len(pf.positions))},
    ]


@router.get("/positions")
def positions():
    pf = Portfolio.load()
    nav = pf.nav
    rows = []
    for p in pf.positions:
        try:
            mark = latest(p.instrument_id).price
        except PricingError:
            mark = p.current_price
        mv = p.quantity * mark
        unrealized = mv - (p.quantity * p.avg_entry_price)
        rows.append({
            "instrument_id": p.instrument_id,
            "side": "LONG" if p.quantity > 0 else "SHORT",
            "asset_class": p.asset_class.value if hasattr(p.asset_class, "value") else str(p.asset_class),
            "quantity": round(p.quantity, 4),
            "entry_price": round(p.avg_entry_price, 4),
            "mark_price": round(mark, 4),
            "market_value": round(mv, 2),
            "pct_nav": round(abs(mv) / nav * 100, 2) if nav > 0 else 0,
            "unrealized_pnl": round(unrealized, 2),
            "unrealized_pct": round((mark / p.avg_entry_price - 1) * 100, 2) if p.avg_entry_price > 0 else 0,
        })
    return rows


@router.get("/recent_fills")
def recent_fills():
    entries = memio.read_short_term()
    fills = sorted(
        [e for e in entries if isinstance(e, TradeEvent)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {"timestamp": f.timestamp.strftime("%Y-%m-%d %H:%M"), "type": f.event_type,
         "instrument_id": f.instrument_id, "quantity": round(f.quantity, 4),
         "fill_price": round(f.fill_price, 4), "slippage": round(f.slippage_cost, 2),
         "commission": round(f.commission_cost, 2), "realized_pnl": round(f.realized_pnl, 2)}
        for f in fills
    ]


@router.get("/equity_curve_chart")
def equity_curve_chart(theme: str = "dark", raw: bool = False):
    return [] if raw else {"data": [], "layout": {}}
