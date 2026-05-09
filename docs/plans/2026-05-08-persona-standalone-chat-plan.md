# Persona Standalone Chat Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Chat" button on every persona card in `/personas` that opens a per-persona slide-over chat drawer. Conversations persist as one rolling thread per persona at `data/personas/conversations/<persona_id>.json`, with a 30-day sliding window for LLM context.

**Architecture:** New `PersonaStandaloneThread` model + `PersonaStandaloneService` that reuses the existing `PersonaAgent.chat()` runtime by passing an empty `approval_payload`. Two new endpoints (`GET /personas/:id/thread`, `POST /personas/:id/thread/messages`). Frontend gets a hook + drawer component that mounts inside `PersonasPage`.

**Tech Stack:** Python 3.11, Pydantic 2.x, FastAPI, pytest. Frontend: Vite/React/TypeScript, Vitest. Reuses everything from the existing persona system — no new deps.

**Reference design:** `docs/plans/2026-05-08-persona-standalone-chat-design.md`

**Key learnings to honor (`learnings.md`):**
- `FakeLLMClient.register(schema_name, handler)` — handler is `(system, user) -> BaseModel`
- `LLMClient.parse(...)` takes `max_tokens=N`
- Subagent worktrees branch from `main` — first step in any subagent prompt: `git rebase main`
- Subagents stage only, parent commits centrally

---

## Task 1: `PersonaStandaloneThread` model

**Files:**
- Modify: `src/castelino/agents/personas/models.py` (append)
- Test: `tests/test_personas_standalone_thread.py`

**Step 1: Failing test**

```python
# tests/test_personas_standalone_thread.py
from datetime import datetime, UTC
from castelino.agents.personas.models import (
    PersonaMessage, PersonaStandaloneThread,
)


def test_thread_round_trips_json():
    t = PersonaStandaloneThread(
        persona_id="krugman",
        started_at=datetime(2026, 5, 1, tzinfo=UTC),
        last_active_at=datetime(2026, 5, 8, tzinfo=UTC),
        messages=[
            PersonaMessage(role="user", text="hi", timestamp=datetime.now(UTC)),
            PersonaMessage(role="assistant", text="hello", timestamp=datetime.now(UTC)),
        ],
    )
    raw = t.model_dump_json()
    loaded = PersonaStandaloneThread.model_validate_json(raw)
    assert loaded == t


def test_thread_default_empty_messages():
    t = PersonaStandaloneThread(
        persona_id="x",
        started_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
    )
    assert t.messages == []
```

**Step 2:** Run `pytest tests/test_personas_standalone_thread.py -v` — expect FAIL.

**Step 3:** Append to `src/castelino/agents/personas/models.py`:

```python
class PersonaStandaloneThread(BaseModel):
    persona_id: str
    started_at: datetime
    last_active_at: datetime
    messages: list[PersonaMessage] = Field(default_factory=list)
```

**Step 4:** Run tests — expect 2/2 PASS.

**Step 5:** `git add` only the two files. Do NOT commit.

Suggested commit msg: `feat(personas): PersonaStandaloneThread model`

---

## Task 2: `PersonaStandaloneService`

**Files:**
- Create: `src/castelino/agents/personas/standalone.py`
- Test: `tests/test_personas_standalone_service.py`

**Step 1: Failing test**

```python
# tests/test_personas_standalone_service.py
import json
from datetime import datetime, UTC, timedelta
from pathlib import Path

import pytest
import yaml

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.agent import PersonaResponse
from castelino.agents.personas.models import (
    PersonaCard, PersonaMessage, PersonaStandaloneThread,
)


@pytest.fixture
def fixture_persona_root(tmp_path):
    pytest.importorskip("chromadb")
    card = PersonaCard(
        persona_id="krugman", full_name="Paul Krugman",
        role="Keynesian economist", tenure="",
        belief_summary="austerity politics, zombie ideas",
        decision_framework=[], signature_phrases=[],
        famous_calls=[], voice_notes="",
    )
    p = tmp_path / "agents" / "krugman" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))
    return tmp_path


def test_send_persists_thread_and_returns_assistant_msg(
    fixture_persona_root, monkeypatch,
):
    from castelino.agents.personas.standalone import PersonaStandaloneService

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="ok", cited_sources=[]))
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )

    svc = PersonaStandaloneService(
        client=fake, data_root=fixture_persona_root, in_memory_store=True,
    )
    msg = svc.send(persona_id="krugman", user_text="What about stagflation?")
    assert msg.role == "assistant"
    assert msg.text == "ok"

    thread = svc.load_thread(persona_id="krugman")
    assert thread.persona_id == "krugman"
    assert len(thread.messages) == 2  # user + assistant
    assert thread.messages[0].role == "user"
    assert thread.messages[1].role == "assistant"


def test_send_reuses_existing_thread(fixture_persona_root, monkeypatch):
    from castelino.agents.personas.standalone import PersonaStandaloneService

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="ok", cited_sources=[]))
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )

    svc = PersonaStandaloneService(
        client=fake, data_root=fixture_persona_root, in_memory_store=True,
    )
    svc.send(persona_id="krugman", user_text="Q1")
    svc.send(persona_id="krugman", user_text="Q2")

    thread = svc.load_thread(persona_id="krugman")
    # 2 user + 2 assistant = 4
    assert len(thread.messages) == 4
    user_msgs = [m for m in thread.messages if m.role == "user"]
    assert [m.text for m in user_msgs] == ["Q1", "Q2"]


def test_send_filters_old_messages_from_llm_context(
    fixture_persona_root, monkeypatch,
):
    """Messages older than 30 days stay on disk but don't go to the LLM."""
    from castelino.agents.personas.standalone import PersonaStandaloneService

    captured_user_prompt = {"text": ""}

    def _handler(system, user):
        captured_user_prompt["text"] = user
        return PersonaResponse(text="r", cited_sources=[])

    fake = FakeLLMClient()
    fake.register("PersonaResponse", _handler)
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )

    svc = PersonaStandaloneService(
        client=fake, data_root=fixture_persona_root, in_memory_store=True,
    )
    # Pre-seed a thread with one ANCIENT user message and one recent
    ancient = datetime.now(UTC) - timedelta(days=60)
    recent = datetime.now(UTC) - timedelta(days=1)
    pre_thread = PersonaStandaloneThread(
        persona_id="krugman",
        started_at=ancient,
        last_active_at=recent,
        messages=[
            PersonaMessage(role="user", text="ANCIENT_TEXT_AAA",
                           timestamp=ancient),
            PersonaMessage(role="user", text="RECENT_TEXT_BBB",
                           timestamp=recent),
        ],
    )
    path = svc._thread_path("krugman")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pre_thread.model_dump_json())

    svc.send(persona_id="krugman", user_text="now")

    # Recent message MUST appear in user prompt; ancient must NOT
    assert "RECENT_TEXT_BBB" in captured_user_prompt["text"]
    assert "ANCIENT_TEXT_AAA" not in captured_user_prompt["text"]

    # But on-disk thread retains all 3 user messages + 1 new assistant
    thread = svc.load_thread(persona_id="krugman")
    user_texts = [m.text for m in thread.messages if m.role == "user"]
    assert "ANCIENT_TEXT_AAA" in user_texts
    assert "RECENT_TEXT_BBB" in user_texts
    assert "now" in user_texts


def test_load_thread_returns_empty_when_no_file(fixture_persona_root, monkeypatch):
    from castelino.agents.personas.standalone import PersonaStandaloneService

    fake = FakeLLMClient()
    svc = PersonaStandaloneService(
        client=fake, data_root=fixture_persona_root, in_memory_store=True,
    )
    thread = svc.load_thread(persona_id="krugman")
    assert thread.persona_id == "krugman"
    assert thread.messages == []
```

**Step 2:** Run — expect FAIL (or skip without chromadb).

**Step 3:** Implement `src/castelino/agents/personas/standalone.py`:

```python
"""Standalone persona chat — free-form, not tied to an approval.

Persists one rolling thread per persona at
data/personas/conversations/<persona_id>.json. 30-day sliding window
for LLM context (older messages stay on disk + UI but don't pay tokens).
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from pathlib import Path

from castelino.agents.base import LLMClient
from castelino.agents.personas.agent import PersonaAgent
from castelino.agents.personas.models import (
    PersonaConversation, PersonaMessage, PersonaStandaloneThread,
)
from castelino.config import get_settings


_LLM_WINDOW_DAYS = 30


class PersonaStandaloneService:
    def __init__(
        self,
        *,
        client: LLMClient,
        data_root: Path | None = None,
        in_memory_store: bool = False,
    ):
        self.client = client
        self.data_root = data_root or Path("data") / "personas"
        self.in_memory_store = in_memory_store
        self._agents: dict[str, PersonaAgent] = {}

    def _agent(self, persona_id: str) -> PersonaAgent:
        if persona_id not in self._agents:
            self._agents[persona_id] = PersonaAgent(
                persona_id=persona_id, client=self.client,
                data_root=self.data_root, in_memory_store=self.in_memory_store,
            )
        return self._agents[persona_id]

    def _thread_path(self, persona_id: str) -> Path:
        return self.data_root / "conversations" / f"{persona_id}.json"

    def load_thread(self, *, persona_id: str) -> PersonaStandaloneThread:
        path = self._thread_path(persona_id)
        if not path.exists():
            now = datetime.now(UTC)
            return PersonaStandaloneThread(
                persona_id=persona_id, started_at=now, last_active_at=now,
            )
        try:
            return PersonaStandaloneThread.model_validate_json(path.read_text())
        except Exception:
            # Move corrupt file aside; return fresh thread
            path.rename(path.with_suffix(".json.bak"))
            now = datetime.now(UTC)
            return PersonaStandaloneThread(
                persona_id=persona_id, started_at=now, last_active_at=now,
            )

    def _save_thread(self, thread: PersonaStandaloneThread) -> None:
        path = self._thread_path(thread.persona_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(thread.model_dump_json(indent=2))

    def send(self, *, persona_id: str, user_text: str) -> PersonaMessage:
        thread = self.load_thread(persona_id=persona_id)

        # Slice to last 30 days for LLM context
        cutoff = datetime.now(UTC) - timedelta(days=_LLM_WINDOW_DAYS)
        windowed = [m for m in thread.messages if m.timestamp >= cutoff]

        # Wrap in PersonaConversation adapter — agent.chat will append
        # the user message + assistant message into adapter.messages.
        adapter = PersonaConversation(
            entry_id="standalone",
            persona_id=persona_id,
            started_at=thread.started_at,
            messages=list(windowed),
        )
        msg = self._agent(persona_id).chat(
            conversation=adapter,
            user_text=user_text,
            approval_payload={},
        )

        # Append the new (user, assistant) pair to the FULL thread
        # (the last two entries in adapter.messages — agent.chat appends
        # both user and assistant in order).
        thread.messages.extend(adapter.messages[-2:])
        thread.last_active_at = datetime.now(UTC)
        self._save_thread(thread)
        return msg
```

**Step 4:** Run tests — expect PASS (or skip if chromadb missing).

**Step 5:** `git add` only the two files. Do NOT commit.

Suggested commit msg: `feat(personas): PersonaStandaloneService with 30-day LLM window`

---

## Task 3: Dashboard endpoints

**Files:**
- Modify: `src/castelino/dashboard/endpoints/personas.py` (append two endpoints)
- Test: `tests/test_personas_standalone_endpoints.py`

**Step 1: Failing test**

```python
# tests/test_personas_standalone_endpoints.py
import json

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def stubbed_dashboard(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    from castelino.agents.base import FakeLLMClient
    from castelino.agents.personas.agent import PersonaResponse
    from castelino.agents.personas.models import PersonaCard
    from castelino.dashboard.main import app

    card = PersonaCard(
        persona_id="krugman", full_name="Paul Krugman",
        role="Keynesian economist", tenure="",
        belief_summary="b", decision_framework=[], signature_phrases=[],
        famous_calls=[], voice_notes="",
    )
    p = tmp_path / "agents" / "krugman" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="standalone-ok",
                                               cited_sources=[]))

    monkeypatch.setattr("castelino.agents.base.get_llm_client", lambda: fake)
    monkeypatch.setattr(
        "castelino.dashboard.endpoints.personas._agents_dir",
        lambda: tmp_path / "agents",
    )
    monkeypatch.setattr(
        "castelino.dashboard.endpoints.personas._data_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )
    return TestClient(app), tmp_path


def test_get_thread_returns_empty_when_no_history(stubbed_dashboard):
    client, _ = stubbed_dashboard
    r = client.get("/personas/krugman/thread")
    assert r.status_code == 200
    body = r.json()
    assert body["persona_id"] == "krugman"
    assert body["messages"] == []


def test_send_message_appends_to_thread(stubbed_dashboard):
    client, _ = stubbed_dashboard
    r = client.post(
        "/personas/krugman/thread/messages",
        json={"text": "thoughts on stagflation?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "assistant"
    assert body["text"] == "standalone-ok"

    # Subsequent GET sees both messages
    r2 = client.get("/personas/krugman/thread")
    assert len(r2.json()["messages"]) == 2
```

**Step 2:** Run — expect FAIL.

**Step 3:** Append to `src/castelino/dashboard/endpoints/personas.py`:

```python
from pydantic import BaseModel

from castelino.agents.base import get_llm_client
from castelino.agents.personas.standalone import PersonaStandaloneService


class _StandaloneMessageBody(BaseModel):
    text: str


def _data_root():
    """Indirection for test monkeypatching."""
    from pathlib import Path
    return Path("data/personas")


def _standalone_service():
    return PersonaStandaloneService(
        client=get_llm_client(), data_root=_data_root(),
    )


@router.get("/personas/{persona_id}/thread")
def get_persona_thread(persona_id: str):
    return _standalone_service().load_thread(persona_id=persona_id)


@router.post("/personas/{persona_id}/thread/messages")
def send_persona_thread_message(persona_id: str, body: _StandaloneMessageBody):
    return _standalone_service().send(
        persona_id=persona_id, user_text=body.text,
    )
```

**Step 4:** Run tests — expect 2/2 PASS (or skip).

**Step 5:** `git add` only the two files. Do NOT commit.

Suggested commit msg: `feat(dashboard): /personas/:id/thread endpoints (GET, POST messages)`

---

## Task 4: Frontend hook + API client

**Files:**
- Modify: `frontend/src/api/personas.ts` (append two functions)
- Modify: `frontend/src/api/types.ts` (append `PersonaStandaloneThread`)
- Create: `frontend/src/hooks/usePersonaStandaloneChat.ts`
- Create: `frontend/src/hooks/__tests__/usePersonaStandaloneChat.test.ts`

**Step 1:** Append to `frontend/src/api/types.ts`:

```typescript
export interface PersonaStandaloneThread {
  persona_id: string;
  started_at: string;
  last_active_at: string;
  messages: PersonaMessage[];
}
```

Append to `frontend/src/api/personas.ts`:

```typescript
import type { PersonaStandaloneThread } from "./types";

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
```

(Make sure `import type { PersonaMessage } ...` already exists, or include it in the new export.)

**Step 2: Failing test** for the hook

```typescript
// frontend/src/hooks/__tests__/usePersonaStandaloneChat.test.ts
import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { usePersonaStandaloneChat } from "../usePersonaStandaloneChat";

describe("usePersonaStandaloneChat", () => {
  beforeEach(() => {
    global.fetch = vi.fn() as unknown as typeof fetch;
  });

  test("loads existing thread on mount", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        persona_id: "krugman",
        started_at: "2026-05-01T00:00:00Z",
        last_active_at: "2026-05-08T00:00:00Z",
        messages: [
          { role: "user", text: "old q",
            timestamp: "2026-05-08T00:00:00Z", citations: [] },
        ],
      }),
    });
    const { result } = renderHook(() => usePersonaStandaloneChat("krugman"));
    await waitFor(() => {
      expect(result.current.messages.length).toBe(1);
    });
    expect(result.current.messages[0].text).toBe("old q");
  });

  test("send appends user + assistant", async () => {
    (global.fetch as any)
      .mockResolvedValueOnce({  // GET thread on mount
        ok: true,
        json: async () => ({
          persona_id: "krugman",
          started_at: "x", last_active_at: "x", messages: [],
        }),
      })
      .mockResolvedValueOnce({  // POST message
        ok: true,
        json: async () => ({
          role: "assistant", text: "Hello.",
          timestamp: "2026-05-08T00:00:00Z", citations: [],
        }),
      });
    const { result } = renderHook(() => usePersonaStandaloneChat("krugman"));
    await waitFor(() => {
      expect(result.current.loaded).toBe(true);
    });
    await act(async () => {
      await result.current.send("hi");
    });
    expect(result.current.messages.length).toBe(2);
    expect(result.current.messages[0].role).toBe("user");
    expect(result.current.messages[1].role).toBe("assistant");
  });
});
```

**Step 3:** Run — expect FAIL.

**Step 4:** Implement `frontend/src/hooks/usePersonaStandaloneChat.ts`:

```typescript
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
```

**Step 5:** Run tests — expect 2/2 PASS (or skip if `npm test` blocked).

**Step 6:** `git add` only the four files. Do NOT commit.

Suggested commit msg: `feat(frontend): persona standalone-chat hook + API client`

---

## Task 5: `PersonaStandaloneChatDrawer` component

**Files:**
- Create: `frontend/src/components/PersonaStandaloneChatDrawer.tsx`
- Create: `frontend/src/components/__tests__/PersonaStandaloneChatDrawer.test.tsx`

**Step 1: Failing test**

```typescript
// frontend/src/components/__tests__/PersonaStandaloneChatDrawer.test.tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { PersonaStandaloneChatDrawer } from "../PersonaStandaloneChatDrawer";

describe("PersonaStandaloneChatDrawer", () => {
  beforeEach(() => {
    global.fetch = vi.fn() as unknown as typeof fetch;
    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({
        persona_id: "krugman",
        started_at: "x", last_active_at: "x", messages: [],
      }),
    });
  });

  test("renders nothing when closed", () => {
    const { container } = render(
      <PersonaStandaloneChatDrawer
        personaId="krugman" personaName="Paul Krugman"
        isOpen={false} onClose={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  test("renders persona name when open", async () => {
    render(
      <PersonaStandaloneChatDrawer
        personaId="krugman" personaName="Paul Krugman"
        isOpen={true} onClose={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/paul krugman/i)).toBeTruthy();
    });
  });

  test("clicking backdrop fires onClose", async () => {
    const onClose = vi.fn();
    render(
      <PersonaStandaloneChatDrawer
        personaId="krugman" personaName="Paul Krugman"
        isOpen={true} onClose={onClose}
      />,
    );
    await waitFor(() => screen.getByText(/paul krugman/i));
    const backdrop = screen.getByTestId("drawer-backdrop");
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalled();
  });
});
```

**Step 2:** Run — expect FAIL.

**Step 3:** Implement `frontend/src/components/PersonaStandaloneChatDrawer.tsx`:

```typescript
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

  // Close on Escape
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
                title={old ? "Older than 30 days — not in current LLM context" : ""}
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
            <div className="text-sm text-muted italic">{personaName} is thinking…</div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="border-t border-border p-3 flex gap-2">
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
```

**Step 4:** Run tests — expect 3/3 PASS (or skip).

**Step 5:** `git add` only the two files. Do NOT commit.

Suggested commit msg: `feat(frontend): PersonaStandaloneChatDrawer slide-over component`

---

## Task 6: Wire "Chat" button into `PersonasPage`

**Files:**
- Modify: `frontend/src/pages/PersonasPage.tsx`

**Step 1:** Add a chat-target state at the top of `PersonasPage`:

```tsx
import { PersonaStandaloneChatDrawer } from "../components/PersonaStandaloneChatDrawer";
// ... existing imports ...

export default function PersonasPage() {
  // ... existing state ...
  const [chatTarget, setChatTarget] = useState<{
    id: string; name: string;
  } | null>(null);
```

**Step 2:** Find the persona-card header where the "Expand" button lives. Add a "Chat" button next to it:

```tsx
<div className="flex items-center gap-2">
  <button
    onClick={() => setChatTarget({ id: p.persona_id, name: p.full_name })}
    className="text-xs text-text-2 hover:text-text px-2 py-1 rounded border border-border bg-blue-50 hover:bg-blue-100"
  >
    Chat
  </button>
  <button
    onClick={() => setExpanded(isExpanded ? null : p.persona_id)}
    className="text-xs text-text-2 hover:text-text px-2 py-1 rounded border border-border"
  >
    {isExpanded ? "Collapse" : "Expand"}
  </button>
</div>
```

(The existing `<button>...{isExpanded ? "Collapse" : "Expand"}</button>` is wrapped in a flex container with the new Chat button to its left.)

**Step 3:** At the bottom of the `PersonasPage` JSX (just before the closing tag), mount the drawer:

```tsx
{chatTarget && (
  <PersonaStandaloneChatDrawer
    personaId={chatTarget.id}
    personaName={chatTarget.name}
    isOpen={true}
    onClose={() => setChatTarget(null)}
  />
)}
```

**Step 4:** Run `cd frontend && npx tsc --noEmit` to type-check (or `npm run build`). Expect: no TypeScript errors. If `npx` is blocked, skip.

**Step 5:** `git add` only `frontend/src/pages/PersonasPage.tsx`. Do NOT commit.

Suggested commit msg: `feat(frontend): wire Chat button on persona cards to standalone drawer`

---

## Task 7: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (extend the persona-agents Completed Work entry)

**Step 1:** In the existing `### 2026-05-08 — Persona Agents (HITL consultation chat)` section, append:

```markdown
- Standalone chat (free-form): each persona card on /personas now has
  a "Chat" button that opens a slide-over drawer with one rolling thread
  per persona, persisted to data/personas/conversations/<id>.json.
  30-day sliding window for LLM context — older messages stay on disk
  and visible (faded) but don't pay tokens. Reuses PersonaAgent.chat()
  with empty approval_payload.
- Two new endpoints: GET /personas/:id/thread, POST /personas/:id/thread/messages
- Design doc: docs/plans/2026-05-08-persona-standalone-chat-design.md
```

**Step 2:** `git add` only `CLAUDE.md`. Do NOT commit.

Suggested commit msg: `docs: log persona standalone-chat completion in CLAUDE.md`

---

## Definition of done

- All Python tests in `tests/test_personas_standalone_*.py` pass (or skip on chromadb-gated cases)
- All frontend tests under `frontend/src/{components,hooks}/__tests__/Persona*Standalone*.test.tsx` pass (or skip if `npm test` is blocked in the harness)
- `npx tsc --noEmit` passes (or build succeeds) — no TypeScript errors from the new components/hooks
- Manual end-to-end check (after `npm run dev` + the FastAPI backend running):
  1. Open `/personas`
  2. Click "Chat" on Krugman's card → drawer opens
  3. Type "thoughts on stagflation?" + send → assistant reply appears with citations
  4. Close drawer (Escape or backdrop click), reopen → previous messages persist
  5. Switch to El-Erian → his thread is independent (empty if first time)
- All commits individually green
