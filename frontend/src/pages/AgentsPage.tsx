import { useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import type { AgentCatalogEntry } from "@/api/endpoints";
import { useAgentCatalog } from "@/hooks/useAgentCatalog";
import { cn } from "@/lib/cn";

const TABS = ["Prompt", "Tools", "Memory", "Output", "Dependencies"] as const;
type Tab = (typeof TABS)[number];

function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return null;
  return (
    <span className={cn("text-[10px] font-semibold px-1.5 py-0.5 rounded-full",
      tier === "reasoning" ? "bg-accent-soft text-accent" : "bg-surface-3 text-muted")}>
      {tier}
    </span>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="font-mono text-xs px-2 py-0.5 border border-border rounded-md bg-surface-2 text-text-2">{children}</span>;
}

function Lane({ title, items, core }: { title: string; items: string[]; core?: boolean }) {
  return (
    <div className={cn("rounded-xl border p-4 min-h-[140px]", core ? "bg-accent-soft border-accent/30" : "border-border")}>
      <div className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">{title}</div>
      <ul className="list-disc pl-4 space-y-1 text-sm">
        {items.length ? items.map((x) => <li key={x}>{x}</li>) : <li className="text-muted list-none -ml-4">—</li>}
      </ul>
    </div>
  );
}

function Detail({ a }: { a: AgentCatalogEntry }) {
  const [tab, setTab] = useState<Tab>("Prompt");
  const core = [a.model ? `${a.tier} · ${a.model}` : a.tier ?? "model n/a", a.output ? `→ ${a.output.name}` : "free-form output"];
  return (
    <Card className="flex flex-col min-h-0">
      <div className="px-6 py-5 border-b border-border">
        <div className="text-lg font-semibold">{a.name}</div>
        <div className="flex flex-wrap gap-2 mt-2">
          <Chip>{a.group}</Chip>
          {a.tier && <Chip>{a.tier}{a.model ? ` · ${a.model}` : ""}</Chip>}
          {a.output && <Chip>→ {a.output.name}</Chip>}
          {a.class_path && <Chip>{a.class_path}</Chip>}
        </div>
        <div className="text-sm text-muted mt-3">{a.summary}</div>
        {a.error && <div className="mt-3 text-xs bg-danger-soft text-danger rounded-lg px-3 py-2">Couldn't read from code: {a.error}</div>}
      </div>
      <div className="flex gap-1 px-4 border-b border-border">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={cn("px-3 py-2.5 text-sm font-medium border-b-2 -mb-px",
              t === tab ? "text-accent border-accent" : "text-muted border-transparent hover:text-text")}>
            {t}
          </button>
        ))}
      </div>
      <div className="p-6 overflow-auto">
        {tab === "Prompt" && (a.prompt ? (
          <>
            <div className="text-xs text-muted mb-2">Live from <span className="font-mono">{a.prompt_source}</span> — the prompt the agent actually runs</div>
            <pre className="whitespace-pre-wrap font-mono text-[12.5px] leading-5 bg-surface-2 border border-border rounded-xl p-4">{a.prompt}</pre>
          </>
        ) : (
          <div className="text-sm text-muted">This agent builds its prompt at runtime from its inputs (see Memory → Reads), so there is no fixed prompt to show.</div>
        ))}
        {tab === "Tools" && (
          <div className="space-y-2.5">
            {a.tools.length ? a.tools.map((t) => (
              <div key={t.name} className="border border-border rounded-xl px-4 py-3">
                <div className="font-mono text-sm font-semibold">{t.name}</div>
                <div className="text-sm text-muted mt-0.5">{t.does}</div>
              </div>
            )) : <div className="text-sm text-muted">No tools. It reasons only over the inputs listed under Memory → Reads.</div>}
            <div className="text-xs text-muted pt-1">From agents.yaml</div>
          </div>
        )}
        {tab === "Memory" && (
          <>
            <div className="grid grid-cols-[1fr_40px_1fr_40px_1fr] items-center">
              <Lane title="Reads" items={a.memory.reads} />
              <div className="text-center text-xl text-muted-2">→</div>
              <Lane title="Agent" items={core} core />
              <div className="text-center text-xl text-muted-2">→</div>
              <Lane title="Writes" items={a.memory.writes} />
            </div>
            <div className="mt-4 text-sm rounded-xl bg-surface-2 border border-border px-4 py-3">
              <b>What persists:</b> {a.memory.persists || "Nothing."}
            </div>
          </>
        )}
        {tab === "Output" && (a.output ? (
          <>
            <div className="text-xs text-muted mb-2">Live from the <span className="font-mono">{a.output.name}</span> schema</div>
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-muted bg-surface-2">
                <tr><th className="text-left px-3 py-2">Field</th><th className="text-left px-3">Type</th><th className="text-left px-3">Meaning</th></tr>
              </thead>
              <tbody>
                {a.output.fields.map((f) => (
                  <tr key={f.name} className="border-t border-border">
                    <td className="px-3 py-2 font-mono text-xs">{f.name}</td>
                    <td className="px-3 font-mono text-xs text-muted">{f.type}</td>
                    <td className="px-3 text-muted">{f.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : <div className="text-sm text-muted">Free-form text output — no schema.</div>)}
        {tab === "Dependencies" && (
          <>
            {a.dependencies.length ? (
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-muted bg-surface-2">
                  <tr><th className="text-left px-3 py-2">API key</th><th className="text-left px-3">Needed</th><th className="text-left px-3">Status</th><th className="text-left px-3">Used for</th></tr>
                </thead>
                <tbody>
                  {a.dependencies.map((d) => (
                    <tr key={d.key} className="border-t border-border">
                      <td className="px-3 py-2.5 font-mono text-xs">{d.key}</td>
                      <td className="px-3">
                        <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full",
                          d.required ? "bg-accent-soft text-accent" : "bg-surface-2 text-muted")}>
                          {d.required ? "Required" : "Optional"}
                        </span>
                      </td>
                      <td className="px-3">
                        <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full",
                          d.set ? "bg-success-soft text-success" : d.required ? "bg-danger-soft text-danger" : "bg-warning-soft text-warning")}>
                          {d.set ? "Set" : "Missing"}
                        </span>
                      </td>
                      <td className="px-3 text-muted">{d.why}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <div className="text-sm text-muted">No API keys needed.</div>}
            <div className="text-xs text-muted pt-3">
              Declared in agents.yaml. Status is checked live in the server's environment (<span className="font-mono">.env</span>); key values are never shown.
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

export default function AgentsPage() {
  const { data, isLoading } = useAgentCatalog();
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const agents = data?.agents ?? [];
  const shown = useMemo(
    () => agents.filter((a) => !q || JSON.stringify(a).toLowerCase().includes(q.toLowerCase())),
    [agents, q],
  );
  const current = agents.find((a) => a.id === picked) ?? agents[0];

  if (isLoading) return <div className="p-8 text-sm text-muted">Loading agents…</div>;

  return (
    <div className="p-8 grid grid-cols-[300px_1fr] gap-5 items-start">
      <Card className="flex flex-col">
        <div className="p-3.5 border-b border-border">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search agents, tools, memory…"
            className="w-full px-3 py-1.5 text-sm border border-border rounded-lg bg-surface-2 outline-none focus:border-accent" />
          <div className="text-xs text-muted mt-2">
            {shown.length} of {agents.length} agents · registry: <span className="font-mono">agents.yaml</span>
          </div>
        </div>
        <div className="p-1.5">
          {(data?.groups ?? []).map((g) => {
            const xs = shown.filter((a) => a.group === g);
            if (!xs.length) return null;
            return (
              <div key={g}>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted px-2.5 pt-3 pb-1">{g}</div>
                {xs.map((a) => (
                  <button key={a.id} onClick={() => setPicked(a.id)}
                    className={cn("w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-sm text-left",
                      a.id === current?.id ? "bg-accent-soft text-accent font-semibold" : "hover:bg-surface-2")}>
                    <span className="truncate">{a.name}</span>
                    <span className="flex items-center gap-1">
                      {a.error && <span className="w-1.5 h-1.5 rounded-full bg-danger" title={a.error} />}
                      <TierBadge tier={a.tier} />
                    </span>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
        {!!data?.unregistered.length && (
          <div className="m-2 p-2.5 border border-dashed border-warning bg-warning-soft rounded-lg text-xs text-warning">
            <b>{data.unregistered.length} agent{data.unregistered.length > 1 ? "s" : ""} not in agents.yaml</b>
            {data.unregistered.map((u) => (
              <div key={u.class_path} className="font-mono mt-1">{u.class_name} <span className="opacity-70">({u.file})</span></div>
            ))}
            <div className="mt-1">Add an entry so its tools and memory show here.</div>
          </div>
        )}
      </Card>
      {current ? <Detail key={current.id} a={current} /> : <Card className="p-8 text-sm text-muted">No agents registered.</Card>}
    </div>
  );
}
