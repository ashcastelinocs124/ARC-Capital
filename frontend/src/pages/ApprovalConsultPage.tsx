import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PersonaPicker } from "../components/PersonaPicker";
import { PersonaChat } from "../components/PersonaChat";
import { PanelDiscussionModal } from "../components/PanelDiscussionModal";
import { listPersonas } from "../api/personas";
import type { PersonaCard } from "../api/types";

export function ApprovalConsultPage() {
  const { entryId } = useParams<{ entryId: string }>();
  const [selectedPersona, setSelectedPersona] = useState<string | null>(null);
  const [personas, setPersonas] = useState<PersonaCard[]>([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [decisionNotes, setDecisionNotes] = useState("");

  useEffect(() => {
    listPersonas().then(setPersonas).catch(() => {});
  }, []);

  if (!entryId) {
    return <div className="p-4 text-red-500">No entry id provided.</div>;
  }

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <div className="mb-4">
        <Link to="/approvals" className="text-sm text-blue-600 hover:underline">
          ← Back to Approval Queue
        </Link>
      </div>

      <h1 className="text-2xl font-semibold mb-4">
        Consult — Approval {entryId}
      </h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* LEFT: pending item summary + decision notes */}
        <div className="space-y-4">
          <div className="border rounded p-4 bg-white">
            <div className="text-xs uppercase text-gray-500">Pending item</div>
            <div className="font-mono text-sm">{entryId}</div>
            <div className="mt-2 text-xs text-gray-500">
              (Item details fetched on the next iteration; for now use this id
              to identify the approval you're consulting on.)
            </div>
          </div>

          <div className="border rounded p-4 bg-white">
            <div className="font-semibold mb-2">Decision notes</div>
            <textarea
              value={decisionNotes}
              onChange={(e) => setDecisionNotes(e.target.value)}
              placeholder="Your reasoning when you approve / reject..."
              className="w-full border rounded p-2 text-sm"
              rows={6}
            />
            <div className="text-xs text-gray-500 mt-1">
              Run a panel and click "Apply Synthesis" to populate this field.
            </div>
          </div>
        </div>

        {/* MIDDLE: persona picker + panel button */}
        <div className="space-y-4">
          <div className="border rounded p-4 bg-white">
            <div className="font-semibold mb-2">Pick a persona</div>
            <PersonaPicker
              selected={selectedPersona}
              onChange={setSelectedPersona}
            />
            <button
              onClick={() => setPanelOpen(true)}
              className="mt-4 w-full px-4 py-2 bg-purple-600 text-white rounded text-sm"
            >
              Run Panel Discussion ▶
            </button>
          </div>
        </div>

        {/* RIGHT: chat thread */}
        <div className="border rounded bg-white min-h-[400px] flex flex-col">
          {selectedPersona ? (
            <PersonaChat entryId={entryId} personaId={selectedPersona} />
          ) : (
            <div className="flex-1 flex items-center justify-center text-sm text-gray-400 italic">
              Pick a persona to start chatting.
            </div>
          )}
        </div>
      </div>

      <PanelDiscussionModal
        entryId={entryId}
        personas={personas}
        isOpen={panelOpen}
        onClose={() => setPanelOpen(false)}
        onApplySynthesis={(text) => {
          setDecisionNotes((prev) =>
            prev.trim() ? `${prev}\n\n${text}` : text,
          );
          setPanelOpen(false);
        }}
      />
    </div>
  );
}
