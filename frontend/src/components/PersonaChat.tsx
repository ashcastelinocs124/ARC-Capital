import { useState } from "react";
import { usePersonaChat } from "../hooks/usePersonaChat";
import type { Citation } from "../api/types";

interface Props {
  entryId: string;
  personaId: string;
}

export function PersonaChat({ entryId, personaId }: Props) {
  const { messages, pending, send } = usePersonaChat(entryId, personaId);
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || pending) return;
    send(input);
    setInput("");
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-3 px-3 py-2">
        {messages.length === 0 && (
          <div className="text-sm text-gray-400 italic">
            Ask the persona a question.
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`rounded-lg px-3 py-2 max-w-[85%] ${
              m.role === "user"
                ? "ml-auto bg-blue-100"
                : "mr-auto bg-gray-100"
            }`}
          >
            <div className="text-xs uppercase opacity-60 mb-1">
              {m.role === "user" ? "You" : "Assistant"}
            </div>
            <div className="whitespace-pre-wrap">{m.text}</div>
            {m.citations && m.citations.length > 0 && (
              <ol className="mt-2 text-xs text-gray-500 space-y-1 border-t border-gray-200 pt-2">
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
        ))}
        {pending && (
          <div className="text-sm text-gray-400 italic">Thinking...</div>
        )}
      </div>
      <form
        onSubmit={handleSubmit}
        className="border-t border-gray-200 p-2 flex gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a question..."
          className="flex-1 px-3 py-2 border rounded-md text-sm"
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
    </div>
  );
}
