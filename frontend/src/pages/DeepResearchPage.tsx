import { useState } from "react";
import { ThesisCharts, type ResolvedChart } from "@/components/ThesisCharts";

type ClarQ = { question: string; why?: string };
type Source = { title: string; url: string; snippet?: string };
type Report = {
  exec_summary: string;
  confidence: number;
  caveats: string[];
  sources: Source[];
  gaps_remaining: string[];
  charts?: ResolvedChart[];
};

export default function DeepResearchPage() {
  const [query, setQuery] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [reworded, setReworded] = useState("");
  const [questions, setQuestions] = useState<ClarQ[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string>("");
  const [report, setReport] = useState<Report | null>(null);

  async function start() {
    setReport(null);
    setStatus("clarifying");
    const r = await fetch("/api/research/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const b = await r.json();
    setSessionId(b.session_id);
    setReworded(b.reworded_query);
    setQuestions(b.clarifying_questions);
    setStatus("awaiting_answers");
  }

  async function submitAnswers() {
    if (!sessionId) return;
    setStatus("researching");
    await fetch(`/api/research/${sessionId}/answers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    });
    poll(sessionId);
  }

  function poll(id: string) {
    const iv = setInterval(async () => {
      const r = await fetch(`/api/research/${id}`);
      const s = await r.json();
      setStatus(s.status);
      if (s.status === "complete") {
        setReport(s.report);
        clearInterval(iv);
      }
      if (s.status === "failed") {
        clearInterval(iv);
      }
    }, 2000);
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Deep Research</h1>
      <textarea
        className="w-full border border-slate-300 bg-white text-black rounded p-2 placeholder-slate-400"
        rows={3}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ask a research question…"
      />
      <button
        className="px-4 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
        onClick={start}
        disabled={!query.trim()}
      >
        Start
      </button>

      {reworded && (
        <p className="text-sm text-slate-400">Reworded: {reworded}</p>
      )}

      {status === "awaiting_answers" && (
        <div className="space-y-3">
          {questions.length === 0 && (
            <p className="text-sm text-slate-400">No clarifications needed.</p>
          )}
          {questions.map((q) => (
            <div key={q.question}>
              <label className="block text-sm font-medium">{q.question}</label>
              {q.why && <p className="text-xs text-slate-500">{q.why}</p>}
              <input
                className="w-full border border-slate-300 bg-white text-black rounded p-1 placeholder-slate-400"
                onChange={(e) =>
                  setAnswers({ ...answers, [q.question]: e.target.value })
                }
              />
            </div>
          ))}
          <button
            className="px-4 py-2 rounded bg-green-600 text-white"
            onClick={submitAnswers}
          >
            Research
          </button>
        </div>
      )}

      {(status === "researching" || status === "synthesizing") && (
        <p className="animate-pulse">Researching… ({status})</p>
      )}

      {status === "failed" && (
        <p className="text-red-400">Research failed. Try again.</p>
      )}

      {report && (
        <div className="space-y-3">
          <h2 className="text-xl font-semibold">
            Answer{" "}
            <span className="text-sm text-slate-400">
              (confidence {report.confidence})
            </span>
          </h2>
          <p className="whitespace-pre-wrap">{report.exec_summary}</p>
          <ThesisCharts charts={report.charts} />
          {report.caveats?.length > 0 && (
            <div>
              <h3 className="font-medium">Caveats</h3>
              <ul className="list-disc ml-5">
                {report.caveats.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <h3 className="font-medium">Sources</h3>
            <ul className="list-disc ml-5">
              {report.sources.map((s) => (
                <li key={s.url}>
                  <a
                    className="text-blue-400 underline"
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {s.title || s.url}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
