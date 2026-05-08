import type {
  PersonaCard, PersonaMessage, PanelDiscussion,
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
