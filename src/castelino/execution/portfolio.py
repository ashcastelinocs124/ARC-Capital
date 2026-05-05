"""Portfolio data model — the deterministic state of the book.

Persisted to `data/portfolio.json` after every execution / mark step.
This is the *book of record*. Agents read it; only the broker, mark loop,
and Portfolio Agent write it (gated by memory.io WriterIdentity).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from castelino.config import get_settings
from castelino.data.instruments import AssetClass, get_instrument


class Position(BaseModel):
    """An open position in a single instrument."""

    instrument_id: str
    quantity: float                # signed: positive = long, negative = short
    avg_entry_price: float         # average fill across opens
    current_price: float           # last mark
    asset_class: AssetClass
    opened_at: datetime
    parent_hypothesis_id: str | None = None
    parent_expression_id: str | None = None
    stop_loss: float | None = None  # absolute price level
    notes: str = ""

    @property
    def market_value(self) -> float:
        """Cash-equivalent gross market value of the position (signed)."""
        inst = get_instrument(self.instrument_id)
        return self.quantity * self.current_price * inst.contract_multiplier

    @property
    def cost_basis(self) -> float:
        inst = get_instrument(self.instrument_id)
        return self.quantity * self.avg_entry_price * inst.contract_multiplier

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis


class NavSnapshot(BaseModel):
    timestamp: datetime
    nav: float
    cash: float
    gross_exposure: float
    net_exposure: float


class Portfolio(BaseModel):
    """Whole-book state. Re-derived NAV after every state mutation."""

    cash: float
    initial_nav: float
    positions: list[Position] = Field(default_factory=list)
    nav_history: list[NavSnapshot] = Field(default_factory=list)
    realized_pnl: float = 0.0
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # ── Derived metrics ────────────────────────────────────────────────────

    @property
    def gross_exposure(self) -> float:
        return sum(abs(p.market_value) for p in self.positions)

    @property
    def net_exposure(self) -> float:
        return sum(p.market_value for p in self.positions)

    @property
    def nav(self) -> float:
        return self.cash + sum(p.market_value for p in self.positions)

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions)

    def position(self, instrument_id: str) -> Position | None:
        return next((p for p in self.positions if p.instrument_id == instrument_id), None)

    def exposure_by_class(self) -> dict[AssetClass, float]:
        out: dict[AssetClass, float] = {ac: 0.0 for ac in AssetClass}
        for p in self.positions:
            out[p.asset_class] += abs(p.market_value)
        return out

    def snapshot(self) -> NavSnapshot:
        return NavSnapshot(
            timestamp=datetime.now(UTC),
            nav=self.nav,
            cash=self.cash,
            gross_exposure=self.gross_exposure,
            net_exposure=self.net_exposure,
        )

    # ── Persistence ────────────────────────────────────────────────────────

    @classmethod
    def default_path(cls) -> Path:
        return get_settings().resolved_paths.data / "portfolio.json"

    @classmethod
    def load(cls, path: Path | None = None) -> "Portfolio":
        path = path or cls.default_path()
        if not path.exists():
            cfg = get_settings()
            return cls(cash=cfg.fund.initial_nav, initial_nav=cfg.fund.initial_nav)
        with path.open("r") as f:
            return cls.model_validate(json.load(f))

    def save(self, path: Path | None = None) -> None:
        path = path or self.default_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.last_updated = datetime.now(UTC)
        with path.open("w") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2, default=str)

    def deep_copy(self) -> "Portfolio":
        """Cheap clone for pure-function execution semantics."""
        return Portfolio.model_validate(self.model_dump(mode="json"))
