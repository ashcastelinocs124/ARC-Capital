import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { usePersonaChat } from "../usePersonaChat";

describe("usePersonaChat", () => {
  beforeEach(() => {
    global.fetch = vi.fn() as unknown as typeof fetch;
  });

  test("sends a message and appends assistant reply", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        role: "assistant",
        text: "Hold quality.",
        timestamp: "2026-05-08T00:00:00Z",
        citations: [],
      }),
    });
    const { result } = renderHook(() => usePersonaChat("H-x", "buffett"));
    await act(async () => {
      await result.current.send("What do you think?");
    });
    await waitFor(() => {
      expect(result.current.messages.length).toBeGreaterThan(0);
    });
    expect(result.current.messages.at(-1)?.text).toBe("Hold quality.");
    expect(result.current.messages.at(-1)?.role).toBe("assistant");
  });

  test("appends user message immediately", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        role: "assistant", text: "ok", timestamp: "x", citations: [],
      }),
    });
    const { result } = renderHook(() => usePersonaChat("H-x", "buffett"));
    await act(async () => {
      await result.current.send("hi");
    });
    expect(result.current.messages[0].role).toBe("user");
    expect(result.current.messages[0].text).toBe("hi");
  });
});
