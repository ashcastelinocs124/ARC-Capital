import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { PersonaPicker } from "../PersonaPicker";

describe("PersonaPicker", () => {
  beforeEach(() => {
    global.fetch = vi.fn() as unknown as typeof fetch;
  });

  test("renders loading state then options", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { persona_id: "buffett", full_name: "Warren Buffett",
          role: "Value investor", tenure: "1965-present",
          belief_summary: "", decision_framework: [],
          signature_phrases: [], famous_calls: [], voice_notes: "" },
        { persona_id: "krugman", full_name: "Paul Krugman",
          role: "Economist", tenure: "",
          belief_summary: "", decision_framework: [],
          signature_phrases: [], famous_calls: [], voice_notes: "" },
      ],
    });

    render(<PersonaPicker selected={null} onChange={() => {}} />);
    expect(screen.getByText(/loading/i)).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText("Warren Buffett")).toBeTruthy();
      expect(screen.getByText("Paul Krugman")).toBeTruthy();
    });
  });

  test("clicking an option fires onChange with persona_id", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { persona_id: "buffett", full_name: "Warren Buffett",
          role: "Value investor", tenure: "",
          belief_summary: "", decision_framework: [],
          signature_phrases: [], famous_calls: [], voice_notes: "" },
      ],
    });

    const onChange = vi.fn();
    render(<PersonaPicker selected={null} onChange={onChange} />);
    await waitFor(() => screen.getByText("Warren Buffett"));
    fireEvent.click(screen.getByText("Warren Buffett"));
    expect(onChange).toHaveBeenCalledWith("buffett");
  });

  test("selected persona is visually marked", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { persona_id: "buffett", full_name: "Warren Buffett",
          role: "Value investor", tenure: "",
          belief_summary: "", decision_framework: [],
          signature_phrases: [], famous_calls: [], voice_notes: "" },
      ],
    });
    render(<PersonaPicker selected="buffett" onChange={() => {}} />);
    await waitFor(() => screen.getByText("Warren Buffett"));
    const option = screen.getByText("Warren Buffett").closest("[data-testid='persona-option']");
    expect(option?.getAttribute("data-selected")).toBe("true");
  });
});
