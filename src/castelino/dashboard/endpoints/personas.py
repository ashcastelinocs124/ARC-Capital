"""Persona roster + standalone-chat endpoints."""
from __future__ import annotations

import json as _json
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from castelino.agents.base import get_llm_client
from castelino.agents.personas.models import PersonaCard
from castelino.agents.personas.rooms import RoomService, RoomSummary
from castelino.agents.personas.standalone import PersonaStandaloneService
from castelino.config import get_settings

router = APIRouter()


def _agents_dir() -> Path:
    return Path("data/personas/agents")


def _data_root() -> Path:
    """Indirection for test monkeypatching."""
    return Path("data/personas")


def _standalone_service() -> PersonaStandaloneService:
    return PersonaStandaloneService(
        client=get_llm_client(), data_root=_data_root(),
    )


class _StandaloneMessageBody(BaseModel):
    text: str


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


@router.get("/personas/{persona_id}/thread")
def get_persona_thread(persona_id: str):
    return _standalone_service().load_thread(persona_id=persona_id)


@router.post("/personas/{persona_id}/thread/messages")
def send_persona_thread_message(
    persona_id: str, body: _StandaloneMessageBody,
):
    return _standalone_service().send(
        persona_id=persona_id, user_text=body.text,
    )


def _room_service() -> RoomService:
    return RoomService(client=get_llm_client(), data_root=_data_root())


class _CreateRoomBody(BaseModel):
    name: str
    member_persona_ids: list[str]
    context: str = ""


class _RoomMessageBody(BaseModel):
    text: str


@router.get("/rooms")
def list_rooms() -> list[RoomSummary]:
    return _room_service().list_rooms()


@router.post("/rooms")
def create_room(body: _CreateRoomBody):
    svc = _room_service()
    return svc.create_room(
        name=body.name,
        member_persona_ids=body.member_persona_ids,
        context=body.context,
    )


@router.get("/rooms/{room_id}")
def get_room(room_id: str):
    svc = _room_service()
    return svc.load_room(room_id)


@router.post("/rooms/{room_id}/messages")
def post_room_message(room_id: str, body: _RoomMessageBody):
    """Streams NDJSON: one RoomMessage per line, as personas finish."""
    svc = _room_service()

    def _gen():
        for msg_dict in svc.send_message(room_id=room_id, user_text=body.text):
            yield _json.dumps(msg_dict) + "\n"

    return StreamingResponse(_gen(), media_type="application/x-ndjson")


@router.delete("/rooms/{room_id}", status_code=204)
def delete_room(room_id: str):
    _room_service().delete_room(room_id)
    return None
