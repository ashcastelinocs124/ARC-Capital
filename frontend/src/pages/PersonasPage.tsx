import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listPersonas } from "../api/personas";
import { PersonaStandaloneChatDrawer } from "../components/PersonaStandaloneChatDrawer";
import type { PersonaCard } from "../api/types";

export default function PersonasPage() {
  const [personas, setPersonas] = useState<PersonaCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [chatTarget, setChatTarget] = useState<{
    id: string; name: string;
  } | null>(null);

  useEffect(() => {
    listPersonas()
      .then(setPersonas)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Persona advisors</h1>
        <p className="text-sm text-muted mt-1">
          Simulated economists and market investors. Consult them during HITL
          approval gates to test theses against varied viewpoints. RAG-backed by
          their own writings — every reply cites the source it draws from.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface-2 p-3 mb-6 text-sm text-text-2">
        Personas are advisors only — they do not participate in the agent
        pipeline. To consult one,{" "}
        <Link to="/approvals" className="text-blue-500 hover:underline">
          go to Approvals
        </Link>{" "}
        and click <span className="font-mono text-xs">Consult →</span> on a
        pending item.
      </div>

      {error && (
        <div className="rounded-lg border border-danger bg-surface-2 p-4 text-sm text-danger">
          Error loading personas: {error}
        </div>
      )}

      {personas === null && !error && (
        <div className="text-sm text-muted">Loading roster…</div>
      )}

      {personas && personas.length === 0 && (
        <div className="rounded-lg border border-border bg-surface-2 p-6 text-sm text-text-2">
          <div className="font-semibold mb-2">No personas built yet.</div>
          <div className="text-muted">
            Run{" "}
            <code className="font-mono text-xs bg-surface-3 px-1.5 py-0.5 rounded">
              ckm persona-build --persona &lt;id&gt; --full-name "X" --role "Y"
            </code>{" "}
            for each persona in the active roster (Krugman, El-Erian, Summers,
            Druckenmiller, Dalio, Tudor Jones).
          </div>
        </div>
      )}

      {personas && personas.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {personas.map((p) => {
            const isExpanded = expanded === p.persona_id;
            return (
              <div
                key={p.persona_id}
                className="rounded-lg border border-border bg-surface p-4 transition hover:border-text-2"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3 min-w-0">
                    {p.image_url ? (
                      <img
                        src={p.image_url}
                        alt={p.full_name}
                        className="w-12 h-12 rounded-full object-cover border border-border shrink-0"
                        loading="lazy"
                      />
                    ) : (
                      <div className="w-12 h-12 rounded-full bg-surface-2 border border-border flex items-center justify-center text-sm font-semibold text-text-2 shrink-0">
                        {p.full_name
                          .split(" ")
                          .map((n) => n[0])
                          .join("")
                          .slice(0, 2)
                          .toUpperCase()}
                      </div>
                    )}
                    <div className="min-w-0">
                      <div className="font-semibold truncate">{p.full_name}</div>
                      <div className="text-xs text-muted">{p.role}</div>
                      {p.tenure && (
                        <div className="text-xs text-muted mt-0.5">{p.tenure}</div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() =>
                        setChatTarget({ id: p.persona_id, name: p.full_name })
                      }
                      className="text-xs px-2 py-1 rounded border border-border bg-blue-50 hover:bg-blue-100 text-blue-700 font-medium"
                    >
                      Chat
                    </button>
                    <button
                      onClick={() =>
                        setExpanded(isExpanded ? null : p.persona_id)
                      }
                      className="text-xs text-text-2 hover:text-text px-2 py-1 rounded border border-border"
                    >
                      {isExpanded ? "Collapse" : "Expand"}
                    </button>
                  </div>
                </div>

                <div className="mt-3 text-sm text-text-2 leading-relaxed">
                  {p.belief_summary}
                </div>

                {p.signature_phrases && p.signature_phrases.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {p.signature_phrases.slice(0, 6).map((phrase) => (
                      <span
                        key={phrase}
                        className="text-xs px-2 py-0.5 rounded bg-surface-2 text-text-2 border border-border"
                      >
                        {phrase}
                      </span>
                    ))}
                  </div>
                )}

                {isExpanded && (
                  <div className="mt-4 space-y-3 border-t border-border pt-3">
                    {p.decision_framework && p.decision_framework.length > 0 && (
                      <div>
                        <div className="text-xs uppercase tracking-wide text-muted mb-1">
                          Decision framework
                        </div>
                        <ul className="text-sm text-text-2 list-disc list-inside space-y-0.5">
                          {p.decision_framework.map((step, i) => (
                            <li key={i}>{step}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {p.famous_calls && p.famous_calls.length > 0 && (
                      <div>
                        <div className="text-xs uppercase tracking-wide text-muted mb-1">
                          Famous calls
                        </div>
                        <ul className="text-sm text-text-2 space-y-1">
                          {p.famous_calls.map((c, i) => (
                            <li key={i}>
                              <span className="font-mono text-xs text-muted">
                                {c.date}
                              </span>{" "}
                              — {c.description}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {p.voice_notes && (
                      <div>
                        <div className="text-xs uppercase tracking-wide text-muted mb-1">
                          Voice
                        </div>
                        <div className="text-sm text-text-2 italic">
                          {p.voice_notes}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {chatTarget && (
        <PersonaStandaloneChatDrawer
          personaId={chatTarget.id}
          personaName={chatTarget.name}
          isOpen={true}
          onClose={() => setChatTarget(null)}
        />
      )}
    </div>
  );
}
