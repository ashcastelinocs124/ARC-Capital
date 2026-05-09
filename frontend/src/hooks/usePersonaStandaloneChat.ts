import { useCallback, useEffect, useState } from "react";
import {
  getPersonaThread, sendPersonaThreadMessage,
} from "../api/personas";
import type { PersonaMessage } from "../api/types";

export function usePersonaStandaloneChat(personaId: string) {
  const [messages, setMessages] = useState<PersonaMessage[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getPersonaThread(personaId)
      .then((thread) => {
        if (!cancelled) {
          setMessages(thread.messages);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => { cancelled = true; };
  }, [personaId]);

  const send = useCallback(
    async (text: string) => {
      setPending(true);
      const userMsg: PersonaMessage = {
        role: "user", text, timestamp: new Date().toISOString(), citations: [],
      };
      setMessages((m) => [...m, userMsg]);
      try {
        const reply = await sendPersonaThreadMessage(personaId, text);
        setMessages((m) => [...m, reply]);
      } finally {
        setPending(false);
      }
    },
    [personaId],
  );

  return { messages, loaded, pending, send };
}
