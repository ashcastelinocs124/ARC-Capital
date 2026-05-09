import { useState } from "react";
import { createRoom } from "../api/personas";
import type { PersonaCard, PersonaRoom } from "../api/types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  personas: PersonaCard[];
  onCreated: (room: PersonaRoom) => void;
}

export function CreateRoomModal({ isOpen, onClose, personas, onCreated }: Props) {
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [context, setContext] = useState("");
  const [pending, setPending] = useState(false);

  if (!isOpen) return null;

  const toggle = (pid: string) => {
    const next = new Set(selected);
    next.has(pid) ? next.delete(pid) : next.add(pid);
    setSelected(next);
  };

  const submit = async () => {
    if (!name.trim() || selected.size === 0) return;
    setPending(true);
    try {
      const room = await createRoom({
        name: name.trim(),
        member_persona_ids: Array.from(selected),
        context: context.trim(),
      });
      onCreated(room);
      setName(""); setSelected(new Set()); setContext("");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center">
      <div className="bg-surface border border-border rounded-lg shadow-xl w-full max-w-lg">
        <div className="border-b border-border px-4 py-3 flex justify-between items-center">
          <div className="font-semibold">Create Room</div>
          <button onClick={onClose} className="text-muted hover:text-text">✕</button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1">Room name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Stagflation Q4"
              className="w-full border border-border rounded-md px-3 py-2 text-sm bg-surface"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Members</label>
            <div className="grid grid-cols-2 gap-1.5">
              {personas.map((p) => (
                <label key={p.persona_id} className="flex items-center gap-2 cursor-pointer text-sm">
                  <input
                    type="checkbox"
                    checked={selected.has(p.persona_id)}
                    onChange={() => toggle(p.persona_id)}
                  />
                  <span>{p.full_name}</span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">
              Room context (optional)
            </label>
            <textarea
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="What are we debating? E.g. 'Stress-testing a long-energy thesis'"
              className="w-full border border-border rounded-md px-3 py-2 text-sm bg-surface"
              rows={2}
            />
          </div>
          <button
            onClick={submit}
            disabled={pending || !name.trim() || selected.size === 0}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-md text-sm disabled:opacity-50"
          >
            {pending ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
