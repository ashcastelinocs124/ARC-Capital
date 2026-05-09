import { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { listPersonas, listRooms, deleteRoom } from "../api/personas";
import { CreateRoomModal } from "../components/CreateRoomModal";
import type { PersonaCard, RoomSummary } from "../api/types";

export default function RoomsPage() {
  const [rooms, setRooms] = useState<RoomSummary[] | null>(null);
  const [personas, setPersonas] = useState<PersonaCard[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const navigate = useNavigate();

  const refresh = useCallback(() => {
    listRooms().then(setRooms);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { listPersonas().then(setPersonas).catch(() => {}); }, []);

  const onDelete = async (roomId: string) => {
    if (!confirm("Delete this room? Messages cannot be recovered.")) return;
    await deleteRoom(roomId);
    refresh();
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Rooms</h1>
          <p className="text-sm text-muted mt-1">
            Multi-persona group chat. Pick personas, set a topic, and let
            them debate while you steer.
          </p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg flex items-center gap-2 text-sm"
        >
          <Plus className="h-4 w-4" /> New Room
        </button>
      </div>

      {rooms === null && <div className="text-sm text-muted">Loading…</div>}

      {rooms && rooms.length === 0 && (
        <div className="rounded-lg border border-border bg-surface-2 p-6 text-sm text-text-2">
          No rooms yet. Click <strong>+ New Room</strong> to start.
        </div>
      )}

      {rooms && rooms.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {rooms.map((r) => (
            <div key={r.room_id} className="rounded-lg border border-border bg-surface p-4">
              <div className="flex justify-between items-start gap-3">
                <Link to={`/rooms/${r.room_id}`} className="font-semibold hover:underline">
                  {r.name}
                </Link>
                <button
                  onClick={() => onDelete(r.room_id)}
                  className="text-xs text-muted hover:text-danger"
                >
                  Delete
                </button>
              </div>
              <div className="text-xs text-muted mt-1">
                {r.member_persona_ids.join(", ")} · {r.message_count} messages
              </div>
              <div className="text-xs text-muted mt-1">
                Last active: {new Date(r.last_active_at).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      )}

      <CreateRoomModal
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
        personas={personas}
        onCreated={(room) => {
          setCreateOpen(false);
          navigate(`/rooms/${room.room_id}`);
        }}
      />
    </div>
  );
}
