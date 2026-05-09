import { useCallback, useEffect, useState } from "react";
import { getRoom, streamRoomMessage } from "../api/personas";
import type { PersonaRoom, RoomMessage } from "../api/types";

export function usePersonaRoom(roomId: string) {
  const [room, setRoom] = useState<PersonaRoom | null>(null);
  const [messages, setMessages] = useState<RoomMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [pendingPersonaId, setPendingPersonaId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRoom(roomId).then((r) => {
      if (cancelled) return;
      setRoom(r);
      setMessages(r.messages);
    });
    return () => { cancelled = true; };
  }, [roomId]);

  const send = useCallback(
    async (text: string) => {
      if (!room) return;
      setPending(true);
      setPendingPersonaId(room.member_persona_ids[0] ?? null);
      let nextIdx = 0;
      try {
        await streamRoomMessage(roomId, text, (msg) => {
          setMessages((m) => [...m, msg]);
          if (msg.speaker !== "user") {
            nextIdx += 1;
            setPendingPersonaId(
              room.member_persona_ids[nextIdx] ?? null,
            );
          }
        });
      } finally {
        setPending(false);
        setPendingPersonaId(null);
      }
    },
    [roomId, room],
  );

  return { room, messages, pending, pendingPersonaId, send };
}
