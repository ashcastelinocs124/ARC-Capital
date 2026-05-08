import { useState } from "react";
import { usePanelDiscussion } from "../hooks/usePanelDiscussion";
import type { PersonaCard, PanelSynthesis } from "../api/types";

interface Props {
  entryId: string;
  personas: PersonaCard[];
  isOpen: boolean;
  onClose: () => void;
  onApplySynthesis: (text: string) => void;
}

function formatSynthesis(s: PanelSynthesis): string {
  const lines: string[] = [];
  if (s.consensus.length > 0) {
    lines.push("Consensus:");
    for (const c of s.consensus) lines.push(`- ${c}`);
  }
  if (s.disagreements.length > 0) {
    lines.push("\nDisagreements:");
    for (const d of s.disagreements) {
      lines.push(`- ${d.axis}:`);
      for (const [pid, stance] of Object.entries(d.positions)) {
        lines.push(`  - ${pid}: ${stance}`);
      }
    }
  }
  if (s.strongest_objection) {
    lines.push(`\nStrongest objection: ${s.strongest_objection}`);
  }
  if (s.recommended_modifications.length > 0) {
    lines.push("\nRecommended modifications:");
    for (const m of s.recommended_modifications) lines.push(`- ${m}`);
  }
  return lines.join("\n");
}

export function PanelDiscussionModal({
  entryId, personas, isOpen, onClose, onApplySynthesis,
}: Props) {
  const { panel, pending, run } = usePanelDiscussion(entryId);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [question, setQuestion] = useState("");

  if (!isOpen) return null;

  const toggle = (pid: string) => {
    const next = new Set(selectedIds);
    if (next.has(pid)) next.delete(pid);
    else next.add(pid);
    setSelectedIds(next);
  };

  const onRun = () => {
    if (selectedIds.size === 0 || !question.trim()) return;
    run(Array.from(selectedIds), question);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="border-b px-4 py-3 flex justify-between items-center">
          <h2 className="text-lg font-semibold">Panel Discussion</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-black">
            ✕
          </button>
        </div>

        <div className="p-4 space-y-4">
          {!panel && (
            <>
              <div>
                <div className="font-semibold mb-2">Choose panelists</div>
                <div className="grid grid-cols-2 gap-2">
                  {personas.map((p) => (
                    <label
                      key={p.persona_id}
                      className="flex items-center gap-2 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(p.persona_id)}
                        onChange={() => toggle(p.persona_id)}
                      />
                      <span>{p.full_name}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <div className="font-semibold mb-2">Question</div>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="What do you want to ask the panel?"
                  className="w-full border rounded p-2 text-sm"
                  rows={3}
                />
              </div>
              <button
                onClick={onRun}
                disabled={pending || selectedIds.size === 0 || !question.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-50"
              >
                {pending ? "Running..." : "Run Panel"}
              </button>
            </>
          )}

          {panel && (
            <>
              <div>
                <div className="font-semibold mb-2">Panel Responses</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {panel.responses.map((r) => (
                    <div
                      key={r.persona_id}
                      className="border rounded p-3 bg-gray-50"
                    >
                      <div className="text-xs uppercase font-bold mb-1">
                        {r.persona_id}
                      </div>
                      <div className="text-sm whitespace-pre-wrap">{r.text}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border rounded p-3 bg-yellow-50">
                <div className="font-semibold mb-2">Synthesis</div>
                {panel.synthesis.consensus.length > 0 && (
                  <div className="text-sm mb-2">
                    <strong>Consensus:</strong>
                    <ul className="list-disc list-inside">
                      {panel.synthesis.consensus.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {panel.synthesis.disagreements.length > 0 && (
                  <div className="text-sm mb-2">
                    <strong>Disagreements:</strong>
                    <ul className="list-disc list-inside">
                      {panel.synthesis.disagreements.map((d, i) => (
                        <li key={i}>
                          <em>{d.axis}</em>:{" "}
                          {Object.entries(d.positions).map(([pid, stance]) => (
                            <span key={pid}> {pid}={stance};</span>
                          ))}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {panel.synthesis.strongest_objection && (
                  <div className="text-sm mb-2">
                    <strong>Strongest objection:</strong>{" "}
                    {panel.synthesis.strongest_objection}
                  </div>
                )}
                {panel.synthesis.recommended_modifications.length > 0 && (
                  <div className="text-sm">
                    <strong>Recommended modifications:</strong>
                    <ul className="list-disc list-inside">
                      {panel.synthesis.recommended_modifications.map((m, i) => (
                        <li key={i}>{m}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => onApplySynthesis(formatSynthesis(panel.synthesis))}
                  className="px-4 py-2 bg-green-600 text-white rounded"
                >
                  Apply Synthesis
                </button>
                <button
                  onClick={onClose}
                  className="px-4 py-2 border rounded"
                >
                  Close
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
