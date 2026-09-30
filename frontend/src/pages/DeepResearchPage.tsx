import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ThesisCharts, type ResolvedChart } from "@/components/ThesisCharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/api/client";
import { useAgentCatalog } from "@/hooks/useAgentCatalog";
import { cn } from "@/lib/cn";

type Source = { title: string; url: string; snippet?: string };
type SubQuestion = { id: string; text: string };
type Finding = {
  sub_question_id: string; summary: string; key_points: string[];
  citations: Source[]; confidence: number; error: string | null;
};
type Report = {
  exec_summary: string; confidence: number; caveats: string[]; gaps_remaining: string[];
  sources: Source[]; findings: Finding[]; charts?: ResolvedChart[];
};
type Session = {
  id: string; original_query: string; reworded_query: string; status: string;
  clarifying_questions: { question: string; why: string }[];
  rounds: { round: number; sub_questions: SubQuestion[]; findings: Finding[] }[];
  report: Report | null; sonar_calls_used: number; error: string | null; updated_at: string;
};
type ListRow = { id: string; original_query: string; status: string; updated_at: string };

const ACTIVE = new Set(["created", "researching", "synthesizing"]);
const SONAR_BUDGET = 15; // config.yaml::deep_research.max_sonar_calls
const STEPS = ["Clarify", "Research", "Synthesize", "Done"];
const STEP_AT: Record<string, number> = {
  created: 0, awaiting_answers: 0, researching: 1, synthesizing: 2, complete: 4, failed: -1,
};

function ago(iso: string) {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (m < 60) return `${m}m ago`;
  if (m < 1440) return `${Math.round(m / 60)}h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
const pct = (x: number) => `${Math.round(x * 100)}%`;
const site = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; } };
const headline = (s: string) => (s.match(/^.*?[.!?](\s|$)/)?.[0] ?? s).trim();

function StatusPill({ status }: { status: string }) {
  const cls = status === "complete" ? "bg-success-soft text-success"
    : status === "failed" ? "bg-danger-soft text-danger" : "bg-warning-soft text-warning";
  return <span className={cn("text-[10px] font-semibold px-1.5 py-0.5 rounded-full", cls)}>{status.replace("_", " ")}</span>;
}

function Stepper({ status }: { status: string }) {
  const at = STEP_AT[status] ?? 0;
  return (
    <Card className="px-5 py-3.5 flex">
      {STEPS.map((n, i) => {
        const done = i < at, now = i === at;
        return (
          <div key={n} className={cn("flex-1 flex items-center gap-2 text-sm", now ? "text-text font-semibold" : "text-muted")}>
            <div className={cn("w-6 h-6 rounded-full border-2 flex items-center justify-center text-[11px] font-semibold shrink-0 bg-white",
              done ? "bg-accent border-accent text-white" : now ? "border-warning text-warning" : "border-border")}>
              {done ? "✓" : i + 1}
            </div>
            {n}
            {i < STEPS.length - 1 && <div className={cn("flex-1 h-0.5 mx-2", done ? "bg-accent" : "bg-border")} />}
          </div>
        );
      })}
    </Card>
  );
}

function Clarify({ s, onSubmit, busy }: { s: Session; onSubmit: (a: Record<string, string>) => void; busy: boolean }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  return (
    <Card>
      <CardHeader>
        <CardTitle>A few questions first</CardTitle>
        {s.reworded_query && <span className="text-xs text-muted">Reworded: “{s.reworded_query}”</span>}
      </CardHeader>
      <CardContent className="space-y-3">
        {s.clarifying_questions.map((q) => (
          <div key={q.question}>
            <div className="text-sm font-medium">{q.question}</div>
            {q.why && <div className="text-xs text-muted">{q.why}</div>}
            <input value={answers[q.question] ?? ""} onChange={(e) => setAnswers({ ...answers, [q.question]: e.target.value })}
              className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded-lg outline-none focus:border-accent" />
          </div>
        ))}
        <div className="flex justify-end gap-2 pt-1">
          <button disabled={busy} onClick={() => onSubmit({})}
            className="px-3.5 py-1.5 text-sm font-semibold rounded-lg border border-border bg-white hover:bg-surface-2 disabled:opacity-50">
            Skip questions, research now
          </button>
          <button disabled={busy} onClick={() => onSubmit(answers)}
            className="px-3.5 py-1.5 text-sm font-semibold rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-50">
            Research with answers
          </button>
        </div>
      </CardContent>
    </Card>
  );
}

function Progress({ s }: { s: Session }) {
  const round = s.rounds[s.rounds.length - 1];
  if (!round) return <Card className="p-5 text-sm text-muted">Planning sub-questions…</Card>;
  const done = new Set(round.findings.map((f) => f.sub_question_id));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Round {round.round} · {round.sub_questions.length} sub-questions in parallel</CardTitle>
        <span className="text-xs text-muted">{s.sonar_calls_used} of {SONAR_BUDGET} web searches used</span>
      </CardHeader>
      <CardContent className="py-1">
        {round.sub_questions.map((q) => (
          <div key={q.id} className="flex justify-between gap-4 py-2.5 border-t border-border first:border-0 text-sm">
            <span>{q.text}</span>
            {done.has(q.id) ? <StatusPill status="complete" />
              : <span className="text-xs text-muted whitespace-nowrap flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full border-2 border-warning border-r-transparent animate-spin" />searching
                </span>}
          </div>
        ))}
        {s.status === "synthesizing" && <div className="text-sm text-muted py-2.5 border-t border-border">Writing the cited report…</div>}
      </CardContent>
    </Card>
  );
}

function ReportView({ s }: { s: Session }) {
  const r = s.report!;
  const subText = Object.fromEntries(s.rounds.flatMap((x) => x.sub_questions).map((q) => [q.id, q.text]));
  const sites = new Set(r.sources.map((x) => site(x.url)));
  const top = headline(r.exec_summary);
  const rest = r.exec_summary.slice(top.length).trim(); // headline is shown above; don't repeat it
  return (
    <div className="space-y-4">
      <Card className="p-5">
        <div className="text-xs text-muted">{s.original_query}</div>
        <div className="text-lg font-semibold mt-1 mb-2.5">{top}</div>
        <div className="flex items-center gap-2.5 text-xs text-muted">
          Confidence
          <div className="w-40 h-2 rounded bg-surface-3 overflow-hidden"><div className="h-full bg-accent" style={{ width: pct(r.confidence) }} /></div>
          <b className="text-text">{pct(r.confidence)}</b> · {s.rounds.length} research round{s.rounds.length === 1 ? "" : "s"} · {r.sources.length} sources
        </div>
        {rest && <p className="text-sm leading-relaxed mt-3 whitespace-pre-wrap">{rest}</p>}
      </Card>

      {r.findings.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Findings by sub-question</CardTitle><span className="text-xs text-muted">click to expand</span></CardHeader>
          {r.findings.map((f, i) => (
            <details key={f.sub_question_id + i} open={i === 0} className="border-t border-border first-of-type:border-0">
              <summary className="px-6 py-3 cursor-pointer text-sm font-medium flex justify-between gap-4 list-none">
                <span>{subText[f.sub_question_id] ?? f.summary}</span>
                {f.error ? <StatusPill status="failed" />
                  : <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-accent-soft text-accent h-fit">{pct(f.confidence)}</span>}
              </summary>
              <div className="px-6 pb-3.5 text-sm text-text-2">
                {f.error ? <div className="text-danger text-xs">{f.error}</div> : <p>{f.summary}</p>}
                {f.key_points.length > 0 && <ul className="list-disc pl-5 my-1.5">{f.key_points.map((k) => <li key={k}>{k}</li>)}</ul>}
                {f.citations.length > 0 && (
                  <div className="text-xs flex flex-wrap gap-x-4 gap-y-1">
                    {f.citations.map((c) => (
                      <a key={c.url} href={c.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                        {c.title || site(c.url)} <span className="text-muted">· {site(c.url)}</span>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </details>
          ))}
        </Card>
      )}

      {!!r.charts?.length && (
        <Card className="px-6 pb-4">
          <ThesisCharts charts={r.charts} />
        </Card>
      )}

      <div className="grid lg:grid-cols-2 gap-4 items-start">
        <Card>
          <CardHeader><CardTitle>Caveats &amp; open gaps</CardTitle></CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            {r.caveats.map((c) => <div key={c}><span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-warning-soft text-warning mr-1.5">caveat</span>{c}</div>)}
            {r.gaps_remaining.map((g) => <div key={g}><span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-danger-soft text-danger mr-1.5">gap</span>{g}</div>)}
            {!r.caveats.length && !r.gaps_remaining.length && <div className="text-muted">None reported.</div>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Sources</CardTitle><span className="text-xs text-muted">{r.sources.length} · {sites.size} sites</span></CardHeader>
          <CardContent className="py-1">
            {r.sources.map((x) => (
              <div key={x.url} className="py-2 border-t border-border first:border-0 text-sm">
                <a href={x.url} target="_blank" rel="noreferrer" className="text-accent font-medium hover:underline">{x.title || x.url}</a>
                <div className="font-mono text-[11px] text-muted">{site(x.url)}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function DeepResearchPage() {
  const [params, setParams] = useSearchParams();
  const id = params.get("id");
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const { data: catalog } = useAgentCatalog();
  const sonarMissing = catalog?.agents
    .find((a) => a.id === "deep_sub_agent")?.dependencies.find((d) => d.key === "PERPLEXITY_API_KEY")?.set === false;

  const { data: listRaw } = useQuery({
    queryKey: ["research_list"],
    queryFn: () => api.get<ListRow[]>("/research"),
    refetchInterval: (q) => (Array.isArray(q.state.data) && q.state.data.some((r) => ACTIVE.has(r.status)) ? 3_000 : false),
  });
  const list = (Array.isArray(listRaw) ? listRaw : []).slice().sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  const { data: sessRaw } = useQuery({
    queryKey: ["research", id],
    queryFn: () => api.get<Session>(`/research/${id}`),
    enabled: !!id,
    refetchInterval: (q) => {
      const st = (q.state.data as Session | undefined)?.status;
      return st && ACTIVE.has(st) ? 2_000 : false;
    },
  });
  const s = sessRaw && !Array.isArray(sessRaw) ? sessRaw : undefined;

  const open = (next: string | null) => setParams(next ? { id: next } : {});

  async function start() {
    setBusy(true); setStartError(null);
    try {
      const b = await api.post<{ session_id: string }>("/research/start", { query });
      open(b.session_id);
      qc.invalidateQueries({ queryKey: ["research_list"] });
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function submit(answers: Record<string, string>) {
    if (!id) return;
    setBusy(true);
    try {
      await api.post(`/research/${id}/answers`, { answers });
      qc.invalidateQueries({ queryKey: ["research", id] });
      qc.invalidateQueries({ queryKey: ["research_list"] });
    } finally { setBusy(false); }
  }

  return (
    <div className="p-8 grid grid-cols-[280px_1fr] gap-5 items-start">
      <Card>
        <div className="px-4 py-3 border-b border-border flex justify-between items-center">
          <span className="text-sm font-semibold">Reports</span>
          <button onClick={() => { open(null); setQuery(""); }}
            className="text-xs font-semibold text-white bg-accent hover:bg-accent-hover rounded-lg px-2.5 py-1">+ New</button>
        </div>
        {list.map((r) => (
          <button key={r.id} onClick={() => open(r.id)}
            className={cn("w-full text-left px-4 py-2.5 border-t border-border first-of-type:border-0",
              r.id === id ? "bg-accent-soft" : "hover:bg-surface-2")}>
            <div className="text-sm leading-snug">{r.original_query}</div>
            <div className="text-[11px] text-muted mt-1 flex items-center gap-1.5"><StatusPill status={r.status} />{ago(r.updated_at)}</div>
          </button>
        ))}
        {list.length === 0 && <div className="px-4 py-6 text-sm text-muted text-center">No reports yet.</div>}
      </Card>

      <div className="space-y-4 min-w-0">
        {sonarMissing && (
          <div className="rounded-xl border border-warning bg-warning-soft px-4 py-2.5 text-sm text-warning">
            <b>PERPLEXITY_API_KEY is missing.</b> Research sub-agents search the web through Perplexity Sonar, so new research
            will fail until it's added to <span className="font-mono">.env</span>. Past reports still open.
          </div>
        )}

        {!id && (
          <Card className="p-4">
            <textarea value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ask a research question…"
              className="w-full h-16 px-3 py-2.5 text-sm border border-border rounded-xl bg-surface-2 resize-none outline-none focus:border-accent" />
            <div className="flex justify-between items-center mt-2.5">
              <span className="text-xs text-muted">Up to 6 sub-questions · ≤{SONAR_BUDGET} web searches · cited report in ~2 min</span>
              <button disabled={busy || !query.trim()} onClick={start}
                className="px-4 py-1.5 text-sm font-semibold rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-50">
                {busy ? "Starting…" : "Research"}
              </button>
            </div>
            {startError && <div className="text-xs text-danger mt-2">Couldn't start: {startError}</div>}
          </Card>
        )}

        {s && (
          <>
            {s.status !== "complete" && <div className="text-sm font-medium">{s.original_query}</div>}
            {s.status !== "failed" && <Stepper status={s.status} />}
            {s.status === "awaiting_answers" && <Clarify s={s} onSubmit={submit} busy={busy} />}
            {(s.status === "researching" || s.status === "synthesizing" || s.status === "created") && <Progress s={s} />}
            {s.status === "failed" && (
              <div className="rounded-xl border border-danger bg-danger-soft px-4 py-3 text-sm text-danger">
                <b>This research failed.</b> {s.error ?? "Unknown error."}
              </div>
            )}
            {s.status === "complete" && s.report && <ReportView s={s} />}
          </>
        )}
      </div>
    </div>
  );
}
