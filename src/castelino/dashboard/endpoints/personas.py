"""Persona roster endpoints."""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from castelino.agents.personas.models import PersonaCard
from castelino.config import get_settings

router = APIRouter()


def _agents_dir() -> Path:
    return Path("data/personas/agents")


@router.get("/personas")
def list_personas() -> list[PersonaCard]:
    cfg = get_settings()
    out = []
    for pid in cfg.personas.active_roster:
        p = _agents_dir() / pid / "profile.yaml"
        if p.exists():
            out.append(PersonaCard.model_validate(yaml.safe_load(p.read_text())))
    return out


@router.get("/personas/{persona_id}")
def get_persona(persona_id: str) -> PersonaCard:
    p = _agents_dir() / persona_id / "profile.yaml"
    if not p.exists():
        raise HTTPException(404, f"Persona {persona_id} not built")
    return PersonaCard.model_validate(yaml.safe_load(p.read_text()))
