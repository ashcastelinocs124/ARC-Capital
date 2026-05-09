import type {
  PersonaCard, PersonaMessage, PanelDiscussion, PersonaStandaloneThread,
  PersonaRoom, RoomMessage, RoomSummary,
} from "./types";

const BASE = "/api"; // proxied to localhost:7779 in dev (vite.config.ts)

export async function sendPersonaMessage(
  entryId: string, personaId: string, text: string,
): Promise<PersonaMessage> {
  const r = await fetch(
    `${BASE}/approvals/${entryId}/conversations/${personaId}/messages`,
    { method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }) },
  );
  if (!r.ok) throw new Error(`send failed: ${r.status}`);
  return r.json();
}

export async function runPanel(
  entryId: string, personas: string[], question: string,
): Promise<PanelDiscussion> {
  const r = await fetch(`${BASE}/approvals/${entryId}/panel`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ personas, question }),
  });
  if (!r.ok) throw new Error(`panel failed: ${r.status}`);
  return r.json();
}

export async function listPersonas(): Promise<PersonaCard[]> {
  const r = await fetch(`${BASE}/personas`);
  if (!r.ok) throw new Error(`personas failed: ${r.status}`);
  return r.json();
}

export async function getPersonaThread(
  personaId: string,
): Promise<PersonaStandaloneThread> {
  const r = await fetch(`${BASE}/personas/${personaId}/thread`);
  if (!r.ok) throw new Error(`thread fetch failed: ${r.status}`);
  return r.json();
}

export async function sendPersonaThreadMessage(
  personaId: string, text: string,
): Promise<PersonaMessage> {
  const r = await fetch(`${BASE}/personas/${personaId}/thread/messages`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw new Error(`send failed: ${r.status}`);
  return r.json();
}

export async function listRooms(): Promise<RoomSummary[]> {
  const r = await fetch(`${BASE}/rooms`);
  if (!r.ok) throw new Error(`list rooms failed: ${r.status}`);
  return r.json();
}

export async function createRoom(body: {
  name: string; member_persona_ids: string[]; context: string;
}): Promise<PersonaRoom> {
  const r = await fetch(`${BASE}/rooms`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`create room failed: ${r.status}`);
  return r.json();
}

export async function getRoom(roomId: string): Promise<PersonaRoom> {
  const r = await fetch(`${BASE}/rooms/${roomId}`);
  if (!r.ok) throw new Error(`get room failed: ${r.status}`);
  return r.json();
}

export async function deleteRoom(roomId: string): Promise<void> {
  const r = await fetch(`${BASE}/rooms/${roomId}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error(`delete room failed: ${r.status}`);
}

/** Streams RoomMessages as personas finish. onMessage fires per message. */
export async function streamRoomMessage(
  roomId: string, text: string,
  onMessage: (m: RoomMessage) => void,
): Promise<void> {
  const r = await fetch(`${BASE}/rooms/${roomId}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok || !r.body) throw new Error(`stream failed: ${r.status}`);
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) {
        try {
          onMessage(JSON.parse(line) as RoomMessage);
        } catch {
          // ignore malformed line
        }
      }
    }
  }
}
