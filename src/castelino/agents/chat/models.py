"""Pydantic models for the `ckm chat` intent router (structured-output)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


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


class Action(BaseModel):
    command: CommandName
    args: dict[str, str] = Field(default_factory=dict)


class AssistantTurn(BaseModel):
    reply: str
    action: Action | None = None