"""Shared types for the backtest regression suite."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


Component = Literal["risk_off", "figure_deviation", "materialize_order"]


class CaseResult(BaseModel):
    case_id: str
    component: Component
    passed: bool
    actual: dict[str, Any]
    expected: dict[str, Any]
    notes: str | None = None
