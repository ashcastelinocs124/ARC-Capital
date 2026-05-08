# Persona Standalone Chat — Design Doc

**Date:** 2026-05-08
**Status:** Design approved, ready for implementation planning

---

## Goal

Let the human chat with any persona directly from the dashboard, without
needing a pending approval to anchor the conversation. One rolling thread
per persona, persisted across sessions, with a 30-day memory window for
LLM context.

## Non-goals

- Personas remain advisors only — never invoked inside the agent pipeline.
- Not a generic chatbot — chat is anchored to a specific persona and
  retrieval still grounds replies in their corpus.
- No multi-persona group chat in this thread (panel mode stays
  approval-bound; that's a different use case).

## Persistence

New file per persona at `data/personas/conversations/<persona_id>.json`:

```python
class PersonaStandaloneThread(BaseModel):
    persona_id: str
    started_at: datetime
    last_active_at: datetime
    messages: list[PersonaMessage]   # reuse existing model
```

Append-only, no truncation on disk. Full history preserved so the curator
agent can mine these threads later for long-term lessons.

## Memory window — 30 days

When constructing the LLM prompt, filter `messages` to those with
`timestamp >= now - 30d`. Older messages stay on disk and visible in the
UI (faded), but don't pay LLM tokens. If the user wants to reference
something older they can quote it back into a fresh message.

This keeps cost bounded as the thread grows. For daily chats: ~30
messages × ~100 tokens each = ~3K tokens history added to the existing
~3.5K system prompt + retrieved chunks. Practical ceiling ~6K input
tokens after 30 days of heavy use.

## Reuse `PersonaAgent.chat()`

The existing runtime already takes a `PersonaConversation` and an
`approval_payload`. We pass the standalone thread (which is shape-
compatible with `PersonaConversation` if we reuse the type or add a
slim wrapper) and an empty `approval_payload={}`. Inside `chat()`, the
retrieval query already falls back to `user_text` alone when no thesis
context is present (`payload.get("thesis", "")` returns empty string).

No new agent class.

## New service `PersonaStandaloneService`

Mirrors `PersonaChatService` but operates on standalone threads instead
of `ApprovalQueue` items:

```python
class PersonaStandaloneService:
    def send(self, *, persona_id, user_text) -> PersonaMessage
    def load_thread(self, *, persona_id) -> PersonaStandaloneThread
```

`send()` flow:
1. Load or create the thread for `persona_id`
2. Slice to messages where `timestamp >= now - 30d` for LLM context
3. Wrap the slice in a `PersonaConversation` adapter (entry_id="standalone")
4. Call `PersonaAgent.chat(conversation=adapter, user_text=..., approval_payload={})`
5. Append the new (user, assistant) pair to the full on-disk thread
6. Update `last_active_at`, persist
7. Return the assistant message

## New endpoints

- `GET /personas/:id/thread` → `PersonaStandaloneThread` (full history)
- `POST /personas/:id/thread/messages` body `{text}` → `PersonaMessage`

Both register in the existing `personas.py` dashboard router (a new file
`dashboard/endpoints/personas.py` was created earlier; we extend it).

## Frontend

Each persona card on `/personas` gets a "Chat" button next to the
existing "Expand" button:

```tsx
<button onClick={() => setChatPersona(p.persona_id)}>Chat</button>
```

When clicked, a slide-over panel opens on the right side (~40% viewport
width) showing the full thread + an input box. Implemented as a new
`PersonaStandaloneChatDrawer` component:

- Loads `GET /personas/:id/thread` on open
- Uses a new `usePersonaStandaloneChat(personaId)` hook that mirrors
  `usePersonaChat` but hits the new endpoints
- Reuses the existing message-bubble + citation rendering
- Older-than-30-days messages render with `opacity-60` and a subtle
  "older — not in context" tooltip
- Closes on Escape or clicking the dimmed backdrop

## Why a slide-over and not a separate route

A drawer keeps the persona roster visible behind, so the user can switch
between personas quickly. A dedicated `/personas/:id` route would force
a full page navigation per persona, breaking flow for "let me also ask
Krugman" thinking. Slide-over preserves the comparison-shopping mental
model.

## What about citations?

Same as approval-bound chat: the persona's response includes
`cited_sources` (from the structured LLM output), which the service
maps back to `Citation` objects from the retrieval hits. Footnotes
render in the message bubble.

## Failure modes

| Failure | Effect | Mitigation |
|---|---|---|
| Thread JSON corrupted | Chat fails to load | Service falls back to fresh thread; corrupt file moved aside with `.bak` suffix; log warning |
| LLM call fails mid-turn | User sees error toast | User message is appended even if assistant fails; user can retry |
| 30-day window contains 0 messages (first chat) | Empty conversation history | Acceptable — system prompt + retrieval handles it |
| Persona profile.yaml missing | 404 | Show "persona not built" with `castelino persona-build` instructions |

## Testing

- Unit: thread load/save round-trip; 30-day filter math; service
  `send()` appends and persists; new endpoints return correct shapes
- Integration: end-to-end with `FakeSTTProvider` + `FakeLLMClient`,
  mocked Chroma — send 3 messages, reload thread, confirm full history
  preserved + LLM only saw windowed slice

## Out of scope (v2+)

- Cross-persona memory ("Krugman, Druckenmiller said X — what do you think?")
- Search across all standalone threads
- Export to PDF / share thread
- Voice input on the standalone chat
