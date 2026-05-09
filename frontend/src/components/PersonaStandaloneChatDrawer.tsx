import { useEffect, useState } from "react";
import { usePersonaStandaloneChat } from "../hooks/usePersonaStandaloneChat";
import type { PersonaMessage, Citation } from "../api/types";

interface Props {
  personaId: string;
  personaName: string;
  isOpen: boolean;
  onClose: () => void;
}

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

function isOldMessage(m: PersonaMessage): boolean {
  return Date.now() - new Date(m.timestamp).getTime() > THIRTY_DAYS_MS;
}

export function PersonaStandaloneChatDrawer({
  personaId, personaName, isOpen, onClose,
}: Props) {
  const { messages, loaded, pending, send } = usePersonaStandaloneChat(personaId);
  const [input, setInput] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || pending) return;
    send(input);
    setInput("");
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div
        data-testid="drawer-backdrop"
        className="flex-1 bg-black/40"
        onClick={onClose}
      />
      <aside className="w-full max-w-xl h-full bg-surface border-l border-border flex flex-col">
        <div className="border-b border-border px-4 py-3 flex items-center justify-between">
          <div>
            <div className="font-semibold">{personaName}</div>
            <div className="text-xs text-muted">Free-form chat</div>
          </div>
          <button
            onClick={onClose}
            className="text-muted hover:text-text px-2 py-1"
            aria-label="Close drawer"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {!loaded && (
            <div className="text-sm text-muted italic">Loading thread…</div>
          )}
          {loaded && messages.length === 0 && (
            <div className="text-sm text-muted italic">
              No history yet. Ask {personaName} something.
            </div>
          )}
          {messages.map((m, i) => {
            const old = isOldMessage(m);
            return (
              <div
                key={i}
                className={`rounded-lg px-3 py-2 max-w-[85%] ${
                  m.role === "user"
                    ? "ml-auto bg-blue-100"
                    : "mr-auto bg-surface-2"
                } ${old ? "opacity-60" : ""}`}
                title={
                  old
                    ? "Older than 30 days — not in current LLM context"
                    : ""
                }
              >
                <div className="text-xs uppercase opacity-60 mb-1">
                  {m.role === "user" ? "You" : personaName}
                </div>
                <div className="whitespace-pre-wrap text-sm">{m.text}</div>
                {m.citations && m.citations.length > 0 && (
                  <ol className="mt-2 text-xs text-muted space-y-1 border-t border-border pt-2">
                    {m.citations.map((c: Citation, idx: number) => (
                      <li key={idx}>
                        <span className="font-mono">[{idx + 1}]</span>{" "}
                        <span className="font-semibold">{c.source}</span>:{" "}
                        <span className="italic">"{c.snippet}"</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            );
          })}
          {pending && (
            <div className="text-sm text-muted italic">
              {personaName} is thinking…
            </div>
          )}
        </div>

        <form
          onSubmit={handleSubmit}
          className="border-t border-border p-3 flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Ask ${personaName} anything…`}
            className="flex-1 px-3 py-2 border border-border rounded-md text-sm bg-surface"
            disabled={pending}
          />
          <button
            type="submit"
            disabled={pending || !input.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </aside>
    </div>
  );
}
