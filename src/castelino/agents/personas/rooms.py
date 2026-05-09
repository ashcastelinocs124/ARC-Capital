"""Multi-persona group chat rooms.

Persisted at data/personas/rooms/<room_id>.json. CRUD operations only;
the round-robin send_message generator is added in a follow-up task.
"""
from __future__ import annotations

import re
from datetime import datetime, UTC
from pathlib import Path

from pydantic import BaseModel

from castelino.agents.base import LLMClient
from castelino.agents.personas.models import PersonaRoom


_SLUG_RX = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    return _SLUG_RX.sub("-", name.lower()).strip("-")


class RoomSummary(BaseModel):
    room_id: str
    name: str
    member_persona_ids: list[str]
    last_active_at: datetime
    message_count: int


class RoomService:
    def __init__(
        self,
        *,
        client: LLMClient,
        data_root: Path | None = None,
        in_memory_store: bool = False,
    ):
        self.client = client
        self.data_root = data_root or Path("data") / "personas"
        self.in_memory_store = in_memory_store

    def _rooms_dir(self) -> Path:
        return self.data_root / "rooms"

    def _room_path(self, room_id: str) -> Path:
        return self._rooms_dir() / f"{room_id}.json"

    def load_room(self, room_id: str) -> PersonaRoom:
        path = self._room_path(room_id)
        if not path.exists():
            now = datetime.now(UTC)
            return PersonaRoom(
                room_id=room_id, name=room_id, member_persona_ids=[],
                created_at=now, last_active_at=now,
            )
        try:
            return PersonaRoom.model_validate_json(path.read_text())
        except Exception:
            path.rename(path.with_suffix(".json.bak"))
            now = datetime.now(UTC)
            return PersonaRoom(
                room_id=room_id, name=room_id, member_persona_ids=[],
                created_at=now, last_active_at=now,
            )

    def _save(self, room: PersonaRoom) -> None:
        d = self._rooms_dir()
        d.mkdir(parents=True, exist_ok=True)
        self._room_path(room.room_id).write_text(
            room.model_dump_json(indent=2),
        )

    def create_room(
        self, *, name: str, member_persona_ids: list[str], context: str = "",
    ) -> PersonaRoom:
        if not member_persona_ids:
            raise ValueError("Room must have at least one member persona")
        now = datetime.now(UTC)
        room = PersonaRoom(
            room_id=_slug(name),
            name=name,
            member_persona_ids=list(member_persona_ids),
            context=context,
            created_at=now,
            last_active_at=now,
            messages=[],
        )
        self._save(room)
        return room

    def list_rooms(self) -> list[RoomSummary]:
        d = self._rooms_dir()
        if not d.exists():
            return []
        out: list[RoomSummary] = []
        for path in sorted(d.glob("*.json")):
            try:
                r = PersonaRoom.model_validate_json(path.read_text())
                out.append(RoomSummary(
                    room_id=r.room_id, name=r.name,
                    member_persona_ids=r.member_persona_ids,
                    last_active_at=r.last_active_at,
                    message_count=len(r.messages),
                ))
            except Exception:
                continue
        return out

    def delete_room(self, room_id: str) -> None:
        path = self._room_path(room_id)
        if path.exists():
            path.unlink()
