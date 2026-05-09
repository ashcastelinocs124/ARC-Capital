import pytest
from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.rooms import RoomService


def test_create_room_writes_file(tmp_path):
    svc = RoomService(client=FakeLLMClient(), data_root=tmp_path, in_memory_store=True)
    room = svc.create_room(
        name="Stagflation Q4",
        member_persona_ids=["krugman", "dalio"],
        context="Stress-testing long energy",
    )
    assert room.room_id == "stagflation-q4"
    assert room.name == "Stagflation Q4"
    path = tmp_path / "rooms" / "stagflation-q4.json"
    assert path.exists()


def test_load_room_round_trips(tmp_path):
    svc = RoomService(client=FakeLLMClient(), data_root=tmp_path, in_memory_store=True)
    created = svc.create_room(
        name="A", member_persona_ids=["x"], context="",
    )
    loaded = svc.load_room(created.room_id)
    assert loaded == created


def test_list_rooms_returns_summaries(tmp_path):
    svc = RoomService(client=FakeLLMClient(), data_root=tmp_path, in_memory_store=True)
    svc.create_room(name="Room A", member_persona_ids=["x"], context="")
    svc.create_room(name="Room B", member_persona_ids=["y", "z"], context="")
    summaries = svc.list_rooms()
    assert len(summaries) == 2
    by_id = {s.room_id: s for s in summaries}
    assert by_id["room-a"].member_persona_ids == ["x"]
    assert by_id["room-b"].member_persona_ids == ["y", "z"]
    assert by_id["room-a"].message_count == 0


def test_delete_room_removes_file(tmp_path):
    svc = RoomService(client=FakeLLMClient(), data_root=tmp_path, in_memory_store=True)
    r = svc.create_room(name="Doomed", member_persona_ids=["x"], context="")
    path = tmp_path / "rooms" / f"{r.room_id}.json"
    assert path.exists()
    svc.delete_room(r.room_id)
    assert not path.exists()


def test_create_room_rejects_empty_members(tmp_path):
    svc = RoomService(client=FakeLLMClient(), data_root=tmp_path, in_memory_store=True)
    with pytest.raises(ValueError):
        svc.create_room(name="x", member_persona_ids=[], context="")


def test_load_room_corrupt_file_recovers(tmp_path):
    svc = RoomService(client=FakeLLMClient(), data_root=tmp_path, in_memory_store=True)
    p = tmp_path / "rooms" / "bad.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not valid json")
    # load_room should NOT raise — moves corrupt file aside, returns fresh empty room
    room = svc.load_room("bad")
    assert room.room_id == "bad"
    assert room.messages == []
    assert (tmp_path / "rooms" / "bad.json.bak").exists()
