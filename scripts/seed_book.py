"""Seed the portfolio with a small starter book for demo runs.

Opens 3 small positions across 3 asset classes so reports have something to
render before the first real pipeline run. NOT used in production replay.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from castelino.config import get_settings
from castelino.execution.broker import OrderType, Side, TradeOrder, execute
from castelino.execution.portfolio import Portfolio
from castelino.execution.pricing import latest


def main() -> None:
    cfg = get_settings()
    pf = Portfolio.load()
    if pf.positions:
        print("portfolio already has positions — refusing to seed.")
        return

    # 2% TLT long, 1.5% GLD long, 1% SPY long. Light, diversified, sane.
    seeds = [
        ("TLT", 0.020, "long"),
        ("GLD", 0.015, "long"),
        ("SPY", 0.010, "long"),
    ]
    for iid, size, _direction in seeds:
        px = latest(iid).price
        notional = size * pf.nav
        qty = round(notional / px, 4)
        order = TradeOrder(
            order_id=f"seed-{uuid.uuid4().hex[:8]}",
            instrument_id=iid,
            order_type=OrderType.MARKET_OPEN,
            side=Side.BUY,
            quantity=qty,
            reference_price=px,
            parent_hypothesis_id="seed-hypothesis",
            notes="Seeded by scripts/seed_book.py for demo.",
        )
        pf, fill = execute(order, pf)
        print(f"  filled {iid}: qty={qty:.4f} @ {fill.fill_price:.4f}")

    pf.save()
    print(f"NAV after seed: ${pf.nav:,.2f}")


if __name__ == "__main__":
    main()
