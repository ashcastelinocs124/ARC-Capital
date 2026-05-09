"""Multi-persona group chat rooms.

Persisted at data/personas/rooms/<room_id>.json. CRUD operations only;
the round-robin send_message generator is added in a follow-up task.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, UTC
from pathlib import Path

from pydantic import BaseModel

from castelino.agents.base import LLMClient
from castelino.agents.personas.agent import PersonaAgent
from castelino.agents.personas.models import (
    PersonaConversation,
    PersonaMessage,
    PersonaRoom,
    RoomMessage,
)


_SLUG_RX = re.compile(r"[^a-z0-9]+")
_LLM_WINDOW_DAYS = 30


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
        self._agents: dict[str, PersonaAgent] = {}

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

    def _agent(self, persona_id: str) -> PersonaAgent | None:
        if persona_id in self._agents:
            return self._agents[persona_id]
        try:
            self._agents[persona_id] = PersonaAgent(
                persona_id=persona_id, client=self.client,
                data_root=self.data_root, in_memory_store=self.in_memory_store,
            )
            return self._agents[persona_id]
        except Exception:
            return None

    def _adapter_for(self, room: PersonaRoom, persona_id: str) -> PersonaConversation:
        cutoff = datetime.now(UTC) - timedelta(days=_LLM_WINDOW_DAYS)
        msgs: list[PersonaMessage] = []
        for m in room.messages:
            if m.timestamp < cutoff:
                continue
            role = "assistant" if m.speaker == persona_id else "user"
            msgs.append(PersonaMessage(
                role=role, text=m.text, timestamp=m.timestamp,
                citations=m.citations,
            ))
        return PersonaConversation(
            entry_id="room", persona_id=persona_id,
            started_at=room.created_at, messages=msgs,
        )

    def send_message(self, *, room_id: str, user_text: str):
        """Generator: yields RoomMessage dicts (user msg first, then one per persona reply)."""
        room = self.load_room(room_id)
        turn = (max((m.turn for m in room.messages), default=0)) + 1

        user_msg = RoomMessage(
            speaker="user", text=user_text,
            timestamp=datetime.now(UTC), turn=turn,
        )
        room.messages.append(user_msg)
        room.last_active_at = datetime.now(UTC)
        self._save(room)
        yield user_msg.model_dump(mode="json")

        for persona_id in room.member_persona_ids:
            agent = self._agent(persona_id)
            if agent is None:
                continue
            room = self.load_room(room_id)  # FRESH state — sees prior personas this turn
            adapter = self._adapter_for(room, persona_id)
            try:
                msg = agent.chat(
                    conversation=adapter,
                    user_text=user_text,
                    approval_payload={"thesis": room.context},
                )
            except Exception:
                continue
            persona_msg = RoomMessage(
                speaker=persona_id, text=msg.text,
                timestamp=datetime.now(UTC), turn=turn,
                citations=msg.citations,
            )
            room.messages.append(persona_msg)
            room.last_active_at = datetime.now(UTC)
            self._save(room)
            yield persona_msg.model_dump(mode="json")
