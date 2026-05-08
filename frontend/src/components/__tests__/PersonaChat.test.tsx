import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { PersonaChat } from "../PersonaChat";

describe("PersonaChat", () => {
  beforeEach(() => {
    global.fetch = vi.fn() as unknown as typeof fetch;
  });

  test("submits text and shows the assistant reply", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        role: "assistant",
        text: "Hold quality.",
        timestamp: "2026-05-08T00:00:00Z",
        citations: [
          { source: "buffett_2008.pdf", snippet: "quality matters", score: 0.9 },
        ],
      }),
    });

    render(<PersonaChat entryId="H-x" personaId="buffett" />);

    const input = screen.getByPlaceholderText(/type a question/i);
    fireEvent.change(input, { target: { value: "Should I buy?" } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("Hold quality.")).toBeTruthy();
    });
    expect(screen.getByText("Should I buy?")).toBeTruthy();
  });

  test("renders citations as footnotes when present", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        role: "assistant",
        text: "Per my 2008 letter, hold quality.",
        timestamp: "x",
        citations: [
          { source: "buffett_2008.pdf", snippet: "hold quality companies",
            score: 0.85 },
        ],
      }),
    });

    render(<PersonaChat entryId="H-x" personaId="buffett" />);
    fireEvent.submit(
      screen.getByPlaceholderText(/type a question/i).closest("form")!,
    );
    await waitFor(() => screen.getByText(/hold quality/i));

    const footnote = await screen.findByText(/buffett_2008\.pdf/i);
    expect(footnote).toBeTruthy();
  });
});
