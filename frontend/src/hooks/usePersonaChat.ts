import { useCallback, useState } from "react";
import { sendPersonaMessage } from "../api/personas";
import type { PersonaMessage } from "../api/types";

export function usePersonaChat(entryId: string, personaId: string) {
  const [messages, setMessages] = useState<PersonaMessage[]>([]);
  const [pending, setPending] = useState(false);

  const send = useCallback(
    async (text: string) => {
      setPending(true);
      const userMsg: PersonaMessage = {
        role: "user", text, timestamp: new Date().toISOString(), citations: [],
      };
      setMessages((m) => [...m, userMsg]);
      try {
        const reply = await sendPersonaMessage(entryId, personaId, text);
        setMessages((m) => [...m, reply]);
      } finally {
        setPending(false);
      }
    },
    [entryId, personaId],
  );

  return { messages, pending, send };
}
