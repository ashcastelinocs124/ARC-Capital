import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { PanelDiscussionModal } from "../PanelDiscussionModal";
import type { PersonaCard } from "../../api/types";

const PERSONAS: PersonaCard[] = [
  { persona_id: "buffett", full_name: "Warren Buffett",
    role: "Value investor", tenure: "",
    belief_summary: "", decision_framework: [],
    signature_phrases: [], famous_calls: [], voice_notes: "" },
  { persona_id: "dalio", full_name: "Ray Dalio",
    role: "All-weather", tenure: "",
    belief_summary: "", decision_framework: [],
    signature_phrases: [], famous_calls: [], voice_notes: "" },
];

describe("PanelDiscussionModal", () => {
  beforeEach(() => {
    global.fetch = vi.fn() as unknown as typeof fetch;
  });

  test("renders persona checkboxes when open", () => {
    render(
      <PanelDiscussionModal
        entryId="H-x"
        personas={PERSONAS}
        isOpen={true}
        onClose={() => {}}
        onApplySynthesis={() => {}}
      />,
    );
    expect(screen.getByText("Warren Buffett")).toBeTruthy();
    expect(screen.getByText("Ray Dalio")).toBeTruthy();
  });

  test("running panel shows responses + synthesis", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        entry_id: "H-x",
        question: "thoughts?",
        responses: [
          { persona_id: "buffett", text: "buffett-response", citations: [] },
          { persona_id: "dalio", text: "dalio-response", citations: [] },
        ],
        synthesis: {
          consensus: ["both like the direction"],
          disagreements: [],
          strongest_objection: "concentration risk",
          recommended_modifications: ["halve size"],
        },
        created_at: "2026-05-08T00:00:00Z",
      }),
    });

    render(
      <PanelDiscussionModal
        entryId="H-x"
        personas={PERSONAS}
        isOpen={true}
        onClose={() => {}}
        onApplySynthesis={() => {}}
      />,
    );

    // Select both, type question, run
    fireEvent.click(screen.getByLabelText("Warren Buffett"));
    fireEvent.click(screen.getByLabelText("Ray Dalio"));
    const textarea = screen.getByPlaceholderText(/question/i);
    fireEvent.change(textarea, { target: { value: "thoughts?" } });
    fireEvent.click(screen.getByText(/run panel/i));

    await waitFor(() => screen.getByText("buffett-response"));
    expect(screen.getByText("dalio-response")).toBeTruthy();
    expect(screen.getByText(/concentration risk/i)).toBeTruthy();
    expect(screen.getByText(/halve size/i)).toBeTruthy();
  });

  test("apply synthesis fires callback with formatted text", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        entry_id: "H-x", question: "q",
        responses: [],
        synthesis: {
          consensus: ["c1"],
          disagreements: [],
          strongest_objection: "o1",
          recommended_modifications: ["m1"],
        },
        created_at: "x",
      }),
    });
    const onApply = vi.fn();
    render(
      <PanelDiscussionModal
        entryId="H-x"
        personas={PERSONAS}
        isOpen={true}
        onClose={() => {}}
        onApplySynthesis={onApply}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText(/question/i),
                     { target: { value: "q" } });
    fireEvent.click(screen.getByText(/run panel/i));
    await waitFor(() => screen.getByText(/o1/));
    fireEvent.click(screen.getByText(/apply synthesis/i));
    expect(onApply).toHaveBeenCalled();
    const arg = onApply.mock.calls[0][0];
    expect(arg).toContain("c1");
    expect(arg).toContain("o1");
    expect(arg).toContain("m1");
  });
});
