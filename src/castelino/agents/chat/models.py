"""Pydantic models for the `ckm chat` intent router (structured-output)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class CommandName(str, Enum):
    # read-only (run freely)
    status = "status"
    queue = "queue"
    research = "research"
    forecast_regime = "forecast_regime"
    forecast_risk = "forecast_risk"
    # mutating / costly (confirm first)
    run = "run"
    approve = "approve"
    reject = "reject"
    reset = "reset"
    mark = "mark"
    # no action — purely conversational
    none = "none"


class AssistantTurn(BaseModel):
    reply: str
    command: CommandName | None = None
    args: dict[str, str] | None = None