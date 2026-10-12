import { useMemo, useRef, useState } from "react";
import { Card } from "@/components/ui/card";
import type { AgentCatalogEntry, AgentSystem } from "@/api/endpoints";
import { useAgentCatalog } from "@/hooks/useAgentCatalog";
import { cn } from "@/lib/cn";
import { AgentArch, FamilyArch, SystemDiagram } from "@/components/SystemDiagram";
import { PageIntro } from "@/components/layout/PageIntro";

const TABS = ["Arch", "Prompt", "Tools", "Memory", "Output", "Dependencies"] as const;
const PUBLIC_TABS = ["Arch"] as const; // the public catalog has no prompts, tools, memory, schemas or keys
type Tab = (typeof TABS)[number];
type Pick = { agent?: string; group?: string; family?: string };

function TierBadge({ tier }: { tier?: string | null }) {
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

function Detail({ a, system, names, open, noArch, admin }: {
  a: AgentCatalogEntry; system?: AgentSystem; names: Record<string, string>;
  open: (p: Pick) => void; noArch?: boolean; // inside a main agent's page the arch is shown once on top
  admin?: boolean;
}) {
  const tabs: readonly Tab[] = !admin ? (noArch ? [] : PUBLIC_TABS) : noArch ? TABS.filter((t) => t !== "Arch") : TABS;
  const [tab, setTab] = useState<Tab>(system && !noArch ? "Arch" : "Prompt");
  const memory = a.memory ?? { reads: [], writes: [], persists: "" };
  const tools = a.tools ?? [];
  const deps = a.dependencies ?? [];
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
      {tabs.length > 0 && <div className="flex gap-1 px-4 border-b border-border overflow-x-auto">
        {tabs.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={cn("px-3 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap",
              t === tab ? "text-accent border-accent" : "text-muted border-transparent hover:text-text")}>
            {t}
          </button>
        ))}
      </div>}
      {tabs.length > 0 && <div className="p-6 overflow-auto">
        {tab === "Arch" && (system ? (
          <AgentArch agentId={a.id} system={system} names={names}
            onAgent={(id) => open({ agent: id })} onSystem={(group) => open({ group })} />
        ) : <div className="text-sm text-muted">No architecture diagram for this agent's group yet (add it under <span className="font-mono">systems:</span> in agents.yaml).</div>)}
        {tab === "Prompt" && (a.prompt ? (
          <>
            <div className="text-xs text-muted mb-2">Live from <span className="font-mono break-all">{a.prompt_source}</span> — the prompt the agent actually runs</div>
            <pre className="whitespace-pre-wrap font-mono text-[12.5px] leading-5 bg-surface-2 border border-border rounded-xl p-4">{a.prompt}</pre>
          </>
        ) : (
          <div className="text-sm text-muted">This agent builds its prompt at runtime from its inputs (see Memory → Reads), so there is no fixed prompt to show.</div>
        ))}
        {tab === "Tools" && (
          <div className="space-y-2.5">
            {tools.length ? tools.map((t) => (
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
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_40px_1fr_40px_1fr] items-center gap-y-2 sm:gap-y-0">
              <Lane title="Reads" items={memory.reads} />
              <div className="text-center text-xl text-muted-2 rotate-90 sm:rotate-0">→</div>
              <Lane title="Agent" items={core} core />
              <div className="text-center text-xl text-muted-2 rotate-90 sm:rotate-0">→</div>
              <Lane title="Writes" items={memory.writes} />
            </div>
            <div className="mt-4 text-sm rounded-xl bg-surface-2 border border-border px-4 py-3">
              <b>What persists:</b> {memory.persists || "Nothing."}
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
            {deps.length ? (
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-muted bg-surface-2">
                  <tr><th className="text-left px-3 py-2">API key</th><th className="text-left px-3">Needed</th><th className="text-left px-3">Status</th><th className="text-left px-3">Used for</th></tr>
                </thead>
                <tbody>
                  {deps.map((d) => (
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
      </div>}
    </Card>
  );
}

/** A main agent (e.g. Update Agent): its architecture once, then every sub-agent's full card. */
function FamilyView({ name, members, system, names, open, admin }: {
  name: string; members: AgentCatalogEntry[]; system?: AgentSystem; names: Record<string, string>;
  open: (p: Pick) => void; admin?: boolean;
}) {
  return (
    <div className="space-y-5">
      <Card className="flex flex-col min-w-0">
        <div className="px-6 py-5 border-b border-border">
          <div className="text-lg font-semibold">{name} <span className="font-normal text-muted">· {members.length} agents</span></div>
          <div className="flex flex-wrap gap-2 mt-2.5">
            {members.map((m) => <Chip key={m.id}>{m.name}{m.model ? ` · ${m.model}` : ""}</Chip>)}
          </div>
        </div>
        <div className="p-6">
          {system ? <FamilyArch ids={members.map((m) => m.id)} system={system} names={names}
            onAgent={(id) => open({ agent: id })} onSystem={(group) => open({ group })} />
            : <div className="text-sm text-muted">No architecture diagram for this group yet.</div>}
        </div>
      </Card>
      {members.map((m) => <Detail key={m.id} a={m} names={names} open={open} noArch admin={admin} />)}
    </div>
  );
}

export default function AgentsPage({ admin = false }: { admin?: boolean }) {
  const { data, isLoading } = useAgentCatalog(admin);
  const [q, setQ] = useState("");
  // an agent id, or a group name for its architecture diagram; null = the first system
  const [picked, setPicked] = useState<Pick | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [groupState, setGroupState] = useState<Record<string, boolean>>({}); // a click overrides the default
  const agents = data?.agents ?? [];
  const systems = data?.systems ?? [];
  const shown = useMemo(
    () => agents.filter((a) => !q || JSON.stringify(a).toLowerCase().includes(q.toLowerCase())),
    [agents, q],
  );
  const family = picked?.family;
  const system = family ? undefined : picked ? systems.find((s) => s.group === picked.group) : systems[0];
  const current = system || family ? undefined : agents.find((a) => a.id === picked?.agent) ?? agents[0];
  const names = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);
  const right = useRef<HTMLDivElement>(null);
  const open = (p: Pick) => { setPicked(p); right.current?.scrollIntoView({ block: "start" }); };
  // every agent system (group) is a dropdown; open when picked, searched, or holding the current agent
  const groupOpen = (g: string, xs: AgentCatalogEntry[]) =>
    groupState[g] ?? (!!q || system?.group === g || xs.some((a) => a.id === current?.id || (!!family && a.family === family)));
  const toggleGroup = (g: string) => {
    const opening = !groupOpen(g, agents.filter((a) => a.group === g));
    setGroupState((prev) => ({ ...prev, [g]: opening }));
    if (opening && systems.some((s) => s.group === g)) open({ group: g });
  };
  const toggleFamily = (f: string) => {
    setExpanded((prev) => { const n = new Set(prev); if (n.has(f) && family === f) n.delete(f); else n.add(f); return n; });
    open({ family: f });
  };
  const agentRow = (a: AgentCatalogEntry, nested = false) => (
    <button key={a.id} onClick={() => open({ agent: a.id })}
      className={cn("w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-sm text-left",
        nested && "text-[13px]",
        a.id === current?.id ? "bg-accent-soft text-accent font-semibold" : "hover:bg-surface-2")}>
      <span className="truncate">{nested && a.family && a.name.startsWith(a.family) ? a.name.slice(a.family.length).replace(/^[\s·]+/, "") : a.name}</span>
      <span className="flex items-center gap-1">
        {a.error && <span className="w-1.5 h-1.5 rounded-full bg-danger" title={a.error} />}
        <TierBadge tier={a.tier} />
      </span>
    </button>
  );

  if (isLoading) return <div className="p-4 md:p-8 text-sm text-muted">Loading agents…</div>;

  return (
    <div className="p-4 md:p-8 space-y-5">
      {admin ? (
        <PageIntro kicker="Admin · Agents" title="Every agent in full: prompts, models, tools, memory, keys"
          steps={["Prompt", "Model", "Tools + data", "Output schema", "Architecture"]}
          when={{ label: `${agents.length} agents`, value: `${systems.length} systems` }}>
          The full private catalog: what each agent is asked to do, which model it runs on, the tools and data it can
          use, its output schema and which API keys it needs.
        </PageIntro>
      ) : (
        <PageIntro kicker="Agents" title="How the agents behind ARC Research work together"
          steps={["Who they are", "How they connect"]}
          when={{ label: `${agents.length} agents`, value: `${systems.length} systems` }}>
          A high-level view of the AI agents that help write ARC's research and how they connect, drawn as one diagram
          per system.
        </PageIntro>
      )}
    <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-5 items-start">
      <Card className="flex flex-col">
        <div className="p-3.5 border-b border-border">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={admin ? "Search agents, tools, memory…" : "Search agents…"}
            className="w-full px-3 py-1.5 text-sm border border-border rounded-lg bg-surface-2 outline-none focus:border-accent" />
          <div className="text-xs text-muted mt-2">
            {shown.length} of {agents.length} agents{admin && <> · registry: <span className="font-mono">agents.yaml</span></>}
          </div>
        </div>
        <div className="p-1.5">
          {(data?.groups ?? []).map((g) => {
            const xs = shown.filter((a) => a.group === g);
            if (!xs.length) return null;
            return (
              <div key={g}>
                <button onClick={() => toggleGroup(g)}
                  className={cn("w-full flex items-center justify-between mt-1 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold uppercase tracking-wider text-left",
                    g === system?.group ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2")}>
                  <span className="flex items-center gap-1.5">
                    <span className={cn("inline-block w-3 transition-transform", groupOpen(g, xs) && "rotate-90")}>▸</span>{g}
                  </span>
                  <span className="text-[10px] font-medium normal-case tracking-normal">{xs.length} agent{xs.length > 1 ? "s" : ""}</span>
                </button>
                {groupOpen(g, xs) && xs.map((a, i) => {
                  if (!a.family) return agentRow(a);
                  if (xs.findIndex((b) => b.family === a.family) !== i) return null; // family drawn at its first member
                  const members = xs.filter((b) => b.family === a.family);
                  const isOpen = expanded.has(a.family) || !!q || members.some((m) => m.id === current?.id);
                  return (
                    <div key={`fam-${a.family}`}>
                      <button onClick={() => toggleFamily(a.family!)}
                        className={cn("w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-sm text-left",
                          family === a.family ? "bg-accent-soft text-accent font-semibold" : "hover:bg-surface-2")}>
                        <span className="flex items-center gap-1.5 truncate">
                          <span className={cn("inline-block w-3 text-muted transition-transform", isOpen && "rotate-90")}>▸</span>{a.family}
                        </span>
                        <span className="text-[11px] text-muted font-normal">{members.length} agents</span>
                      </button>
                      {isOpen && <div className="ml-4 pl-1 border-l border-border">{members.map((m) => agentRow(m, true))}</div>}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
        {admin && !!data?.unregistered?.length && (
          <div className="m-2 p-2.5 border border-dashed border-warning bg-warning-soft rounded-lg text-xs text-warning">
            <b>{data?.unregistered?.length} agent{(data?.unregistered?.length ?? 0) > 1 ? "s" : ""} not in agents.yaml</b>
            {data?.unregistered?.map((u) => (
              <div key={u.class_path} className="font-mono mt-1">{u.class_name} <span className="opacity-70">({u.file})</span></div>
            ))}
            <div className="mt-1">Add an entry so its tools and memory show here.</div>
          </div>
        )}
      </Card>
      <div ref={right} className="min-w-0 scroll-mt-4">
      {system ? (
        <div className="space-y-5">
          <Card className="flex flex-col min-w-0">
            <SystemDiagram system={system} names={names} onAgent={(id) => open({ agent: id })} onSystem={(group) => open({ group })} />
          </Card>
          {agents.filter((a) => a.group === system.group).map((m) => <Detail key={m.id} a={m} names={names} open={open} noArch admin={admin} />)}
        </div>
      ) : family ? <FamilyView name={family} members={agents.filter((a) => a.family === family)} names={names} open={open} admin={admin}
        system={systems.find((s) => s.group === agents.find((a) => a.family === family)?.group)} />
      : current ? <Detail key={current.id} a={current} names={names} open={open} admin={admin}
        system={systems.find((s) => s.group === current.group)} /> : <Card className="p-4 md:p-8 text-sm text-muted">No agents registered.</Card>}
      </div>
    </div>
    </div>
  );
}
