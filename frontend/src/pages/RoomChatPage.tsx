import { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { listPersonas } from "../api/personas";
import { usePersonaRoom } from "../hooks/usePersonaRoom";
import type { PersonaCard, RoomMessage } from "../api/types";

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;
const isOld = (m: RoomMessage) =>
  Date.now() - new Date(m.timestamp).getTime() > THIRTY_DAYS_MS;

export default function RoomChatPage() {
  const { roomId } = useParams<{ roomId: string }>();
  const { room, messages, pending, pendingPersonaId, send } =
    usePersonaRoom(roomId!);
  const [personas, setPersonas] = useState<Record<string, PersonaCard>>({});
  const [input, setInput] = useState("");

  useEffect(() => {
    listPersonas().then((list) => {
      setPersonas(Object.fromEntries(list.map((p) => [p.persona_id, p])));
    }).catch(() => {});
  }, []);

  if (!room) return <div className="p-6 text-sm text-muted">Loading room…</div>;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || pending) return;
    send(input);
    setInput("");
  };

  return (
    <div className="flex flex-col h-screen">
      <div className="border-b border-border px-4 py-3 flex items-center gap-3">
        <Link to="/rooms" className="text-muted hover:text-text">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="font-semibold truncate">{room.name}</div>
          {room.context && (
            <div className="text-xs text-muted truncate">{room.context}</div>
          )}
        </div>
        <div className="flex -space-x-2">
          {room.member_persona_ids.map((pid) => {
            const p = personas[pid];
            return p?.image_url ? (
              <img
                key={pid}
                src={p.image_url}
                alt={p.full_name}
                title={p.full_name}
                className="w-8 h-8 rounded-full border-2 border-surface object-cover"
              />
            ) : (
              <div
                key={pid}
                title={p?.full_name ?? pid}
                className="w-8 h-8 rounded-full bg-surface-2 border-2 border-surface flex items-center justify-center text-xs"
              >
                {(p?.full_name ?? pid).split(" ").map((n) => n[0]).join("").slice(0,2).toUpperCase()}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 max-w-3xl mx-auto w-full">
        {messages.length === 0 && (
          <div className="text-sm text-muted italic text-center py-8">
            Send a message to kick off the discussion.
          </div>
        )}
        {messages.map((m, i) => {
          const old = isOld(m);
          const isUser = m.speaker === "user";
          const persona = !isUser ? personas[m.speaker] : null;
          return (
            <div
              key={i}
              className={`flex gap-2 ${isUser ? "justify-end" : "justify-start"}`}
            >
              {!isUser && persona?.image_url && (
                <img src={persona.image_url} alt={persona.full_name}
                  className="w-8 h-8 rounded-full object-cover flex-shrink-0 mt-1" />
              )}
              {!isUser && !persona?.image_url && (
                <div className="w-8 h-8 rounded-full bg-surface-2 flex items-center justify-center text-xs mt-1 flex-shrink-0">
                  {(persona?.full_name ?? m.speaker).split(" ").map(n=>n[0]).join("").slice(0,2).toUpperCase()}
                </div>
              )}
              <div
                className={`rounded-lg px-3 py-2 max-w-[75%] ${
                  isUser ? "bg-blue-100" : "bg-surface-2"
                } ${old ? "opacity-60" : ""}`}
                title={old ? "Older than 30 days — not in current LLM context" : ""}
              >
                <div className="text-xs uppercase font-bold opacity-60 mb-1">
                  {isUser ? "You" : persona?.full_name ?? m.speaker}
                </div>
                <div className="text-sm whitespace-pre-wrap">{m.text}</div>
                {m.citations && m.citations.length > 0 && (
                  <ol className="mt-2 text-xs text-muted space-y-0.5 border-t border-border pt-1.5">
                    {m.citations.map((c, idx) => (
                      <li key={idx}>
                        <span className="font-mono">[{idx+1}]</span>{" "}
                        <span className="font-semibold">{c.source}</span>:{" "}
                        <span className="italic">"{c.snippet}"</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          );
        })}
        {pending && pendingPersonaId && (
          <div className="text-sm text-muted italic">
            {personas[pendingPersonaId]?.full_name ?? pendingPersonaId} is thinking…
          </div>
        )}
      </div>

      <form
        onSubmit={submit}
        className="border-t border-border p-3 flex gap-2 max-w-3xl mx-auto w-full"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Pose a question to the room…"
          disabled={pending}
          className="flex-1 px-3 py-2 border border-border rounded-md text-sm bg-surface"
        />
        <button
          type="submit"
          disabled={pending || !input.trim()}
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
