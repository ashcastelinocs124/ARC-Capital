import { useState } from "react";
import { cn } from "@/lib/cn";
import { PLAIN, SECTIONS, SECTION_LABEL, trade, type Fact, type Idea, type Msg, type Option, type Status } from "./api";

// The pieces of one idea's screen (approved mockup: docs/superpowers/specs/2026-10-15-trade-lab/trade-lab-mock.html).
const STEPS = ["Frame", "Debate", "Your view", "Research", "Pick charts", "Draft"];
const STEP_OF: Record<Status, number> = {
  framing: 0, debating: 1, awaiting_view: 2, researching: 3, awaiting_charts: 4, writing: 5, draft_ready: 6,
};
// news blue / technical purple: the Week Ahead category colours (index.css), not new hexes
const NEWS = "text-[rgb(var(--c-cat-jobs))] bg-[rgb(var(--c-cat-jobs)_/_0.12)]";
const TECH = "text-[rgb(var(--c-cat-ai))] bg-[rgb(var(--c-cat-ai)_/_0.12)]";

export function FactChip({ id, facts }: { id: string; facts: Fact[] }) {
  const [open, setOpen] = useState(false);
  const f = facts.find((x) => x.id === id);
  const tone = id.startsWith("N") ? NEWS : id.startsWith("T") ? TECH : "text-accent bg-accent-soft-2";
  return (
    <span className="relative">
      <button onClick={() => setOpen((o) => !o)} className={cn("rounded px-1 font-mono text-[10px] font-bold", tone)}>{id}</button>
      {open && f && (
        <span className="absolute left-0 top-5 z-20 block w-72 rounded-xl border border-border-strong bg-surface-3 p-3 text-xs shadow-lg">
          <span className="block text-text">{f.text}</span>
          <span className="mt-1 block text-muted">{f.source_title}</span>
          {f.source_url && <a href={f.source_url} target="_blank" rel="noreferrer" className="mt-1 block font-semibold text-accent">Open the source ↗</a>}
        </span>
      )}
    </span>
  );
}

const Chips = ({ ids, facts }: { ids: string[]; facts: Fact[] }) => (
  <>{ids.map((i) => <span key={i}> <FactChip id={i} facts={facts} /></span>)}</>
);

export function Header({ idea }: { idea: Idea }) {
  const at = STEP_OF[idea.status];
  const running = idea.job?.state === "running" || idea.job?.state === "queued";
  return (
    <div className="rounded-2xl border border-border bg-surface px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Trade idea · {idea.created_at.slice(0, 10)}</div>
          <h2 className="font-serif text-2xl font-bold leading-tight">{idea.frame?.title ?? idea.idea}</h2>
          <p className="text-[13px] italic text-muted">“{idea.idea}”</p>
        </div>
        <div className="flex flex-wrap gap-1.5 text-xs font-semibold">
          <span className="rounded-full bg-surface-3 px-2.5 py-1">Round {idea.round} of 3</span>
          <span className="rounded-full bg-surface-3 px-2.5 py-1">{idea.facts.length} facts</span>
          <span className="rounded-full bg-surface-3 px-2.5 py-1">${idea.cost_usd.toFixed(2)}</span>
        </div>
      </div>
      <ol className="mt-4 grid grid-cols-6 text-center text-xs">
        {STEPS.map((s, i) => {
          const done = i < at, now = i === at, you = i === 2 || i === 4;
          return (
            <li key={s} className="flex flex-col items-center gap-1.5">
              <span className={cn("grid h-6 w-6 place-items-center rounded-full border-2 text-[11px] font-bold",
                done ? "border-accent bg-accent text-on-accent"
                  : now ? (running ? "animate-pulse border-info text-info" : "border-warning bg-warning-soft text-warning")
                  : "border-border-strong text-muted",
                you && !done && "border-dashed")}>{done ? "✓" : i + 1}</span>
              <span className={cn(done ? "text-text-2" : now ? "font-semibold text-warning" : "text-muted")}>{s}</span>
            </li>
          );
        })}
      </ol>
      {idea.fallbacks.length > 0 && <p className="mt-2 text-[11px] text-muted">Fallback used: {idea.fallbacks[idea.fallbacks.length - 1]}</p>}
    </div>
  );
}

export function FrameStrip({ idea, onIdea }: { idea: Idea; onIdea: (i: Idea) => void }) {
  const f = idea.frame;
  const [edit, setEdit] = useState(false);
  const [thesis, setThesis] = useState(f?.thesis ?? "");
  const [wrong, setWrong] = useState(f?.prove_wrong.join("\n") ?? "");
  const [note, setNote] = useState<string | null>(null);
  if (!f) return null;
  const save = () =>
    trade.setFrame(idea.id, { ...f, thesis: thesis.trim(), prove_wrong: wrong.split("\n").map((x) => x.trim()).filter(Boolean) })
      .then((i) => { onIdea(i); setEdit(false); setNote("Saved. Re-run the debate to argue the new framing."); })
      .catch((e) => setNote(String(e.message ?? e)));
  return (
    <div className="rounded-2xl border border-border bg-surface">
      <div className="grid md:grid-cols-[1.5fr_1fr_.6fr_1.5fr]">
        <div className="p-4"><div className="eyebrow">Thesis</div><p className="mt-1 text-[13px] text-text-2">{f.thesis}</p></div>
        <div className="border-border p-4 md:border-l"><div className="eyebrow">Stand-ins</div>
          <div className="mt-1 flex flex-wrap gap-1">{f.stand_ins.map((s) => (
            <span key={s.ticker} className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[11px] font-semibold">{s.ticker}</span>))}</div></div>
        <div className="border-border p-4 md:border-l"><div className="eyebrow">Horizon</div><p className="mt-1 font-serif text-xl font-bold">{f.horizon_months} mo</p></div>
        <div className="border-border p-4 md:border-l"><div className="eyebrow">What would prove it wrong</div><p className="mt-1 text-[13px] text-danger">{f.prove_wrong.join(" · ")}</p></div>
      </div>
      {idea.status === "awaiting_view" && (
        <div className="border-t border-border px-4 py-2.5">
          {!edit ? <button onClick={() => setEdit(true)} className="text-xs font-semibold text-accent">Edit the framing</button> : (
            <div className="grid gap-2 md:grid-cols-2">
              <textarea rows={2} value={thesis} onChange={(e) => setThesis(e.target.value)} className="rounded-xl border border-border-strong bg-surface-2 px-3 py-2 text-sm" />
              <textarea rows={2} value={wrong} onChange={(e) => setWrong(e.target.value)} placeholder="One test per line"
                className="rounded-xl border border-border-strong bg-surface-2 px-3 py-2 text-sm" />
              <div className="flex gap-2 md:col-span-2">
                <button onClick={save} className="rounded-full bg-accent px-3 py-1 text-xs font-semibold text-on-accent">Save</button>
                <button onClick={() => setEdit(false)} className="text-xs text-muted">Cancel</button>
              </div>
            </div>
          )}
          {note && <p className="mt-1 text-xs text-muted">{note}</p>}
        </div>
      )}
    </div>
  );
}

export function Debate({ idea }: { idea: Idea }) {
  const turn = (side: "bull" | "bear", r: number) => idea.turns.find((t) => t.side === side && t.round === r);
  return (
    <div className="rounded-2xl border border-border bg-surface p-4">
      <div className="grid grid-cols-[1fr_96px_1fr] gap-y-2.5">
        <div className="text-xs font-bold uppercase tracking-wider text-accent">↗ Bull</div><div />
        <div className="text-xs font-bold uppercase tracking-wider text-danger">↘ Bear</div>
        {[0, 1, 2].map((r) => [
          <div key={`b${r}`} className="rounded-xl border-l-[3px] border-accent bg-accent-soft/60 p-3 text-[13.5px] leading-relaxed text-text-2">
            {turn("bull", r)?.text}<Chips ids={turn("bull", r)?.fact_ids ?? []} facts={idea.facts} /></div>,
          <div key={`m${r}`} className="grid place-items-center">
            <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-muted">{["Opening", "Rebuttal 1", "Rebuttal 2"][r]}</span></div>,
          <div key={`r${r}`} className="rounded-xl border-l-[3px] border-danger bg-danger-soft/50 p-3 text-[13.5px] leading-relaxed text-text-2">
            {turn("bear", r)?.text}<Chips ids={turn("bear", r)?.fact_ids ?? []} facts={idea.facts} /></div>,
        ])}
      </div>
      {idea.moderation && (
        <div className="mt-4 grid gap-4 border-t border-border pt-3 md:grid-cols-2">
          <div><div className="eyebrow text-accent">Moderator · settled</div>
            {idea.moderation.settled.map((s, i) => <p key={i} className="mt-2 text-[13.5px] text-text-2">✓ {s.point}<Chips ids={s.fact_ids} facts={idea.facts} /></p>)}
            <p className="mt-3 text-xs text-muted">No winner. ARC doesn't make buy or sell calls.</p></div>
          <div><div className="eyebrow text-warning">Still open</div>
            {idea.moderation.open.map((q, i) => <p key={i} className="mt-2 text-[13.5px] text-text-2">? {q.question}</p>)}</div>
        </div>
      )}
    </div>
  );
}

const KIND: Record<string, [string, string]> = {
  claim: ["Your claim · to verify", NEWS],
  question: ["Your question", "text-warning bg-warning-soft"],
  moderator: ["Moderator · still open", "text-muted bg-surface-3"],
};

function SendBar({ items, remove, onSend, label, busy }: {
  items: Idea["research"]; remove: (id: string) => void; onSend: () => void; label: string; busy: boolean;
}) {
  return (
    <>
      {items.map((r) => (
        <div key={r.id} className="mt-2 flex items-start justify-between gap-2 rounded-xl border border-border bg-surface-2 px-3 py-2 text-[13px] text-text-2">
          <div><span className={cn("mb-0.5 inline-block rounded px-1.5 text-[10px] font-bold uppercase tracking-wide", KIND[r.kind][1])}>{KIND[r.kind][0]}</span>
            <div>{r.text}</div></div>
          <button onClick={() => remove(r.id)} className="text-muted-2 hover:text-danger" aria-label="Remove">×</button>
        </div>
      ))}
      <div className="mt-3 flex justify-end">
        <button disabled={busy || items.length === 0} onClick={onSend}
          className="rounded-full bg-accent px-4 py-2 text-[13px] font-semibold text-on-accent disabled:opacity-40">{label} →</button>
      </div>
    </>
  );
}

function decisionLabel(m: Msg): string {
  const d = m.decision ?? {};
  if (m.action === "research") return `↳ Decisions API: yes (${(d.research ?? 0).toFixed(2)}) · added to research`;
  return `Decisions API: no (${(d.research ?? 0).toFixed(2)}) · not added`;
}

// One Talk 2 trail line ("Edited The bear case · Claude Haiku 5.5 · $0.003") as a chip and the rest.
function Step({ line }: { line: string }) {
  const bad = /^(Not edited|The Substack draft didn't)/.test(line);
  const fell = line.includes("failed the number check twice");
  const head = bad ? "Not done" : fell ? "Fallback" : line.split(" ")[0];
  const rest = bad || fell ? line : line.slice(head.length + 1);
  const tone = bad ? "bg-danger-soft text-danger" : fell ? "bg-text text-surface"
    : head === "Searched" ? "bg-warning-soft text-warning" : head === "Answered" ? "bg-surface-3 text-muted" : "bg-accent-soft text-accent";
  return (
    <div className="flex items-baseline gap-1.5 text-[11.5px] text-muted">
      <span className={cn("whitespace-nowrap rounded-full px-1.5 text-[10px] font-bold uppercase tracking-wide", tone)}>{head}</span>{rest}
    </div>
  );
}

export function Talk({ idea, n, onIdea, onSend, sendLabel, busy }: {
  idea: Idea; n: 1 | 2; onIdea: (i: Idea) => void; onSend?: () => void; sendLabel?: string; busy: boolean;
}) {
  const [to, setTo] = useState("ARC");
  const [text, setText] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const msgs = idea.talk.filter((m) => m.talk === n);
  const items = idea.research.filter((r) => r.round === idea.round && !r.removed);
  const working = n === 2 && busy && idea.job?.step === "talk";
  const send = () => {
    const m = text.trim();
    if (!m || waiting) return;
    setWaiting(true); setError(null);
    trade.talk(idea.id, n, to, m).then((r) => { onIdea(r.idea); setText(""); })
      .catch((e) => setError(String(e.message ?? e))).finally(() => setWaiting(false));
  };
  const remove = (item: string) => trade.removeItem(idea.id, item).then(onIdea).catch((e) => setError(String(e.message ?? e)));
  return (
    <div className={cn("grid rounded-2xl border border-warning/50 bg-surface", n === 1 && "md:grid-cols-[1.45fr_1fr]")}>
      <div className={cn("flex flex-col gap-2.5 p-4", n === 1 && "border-border md:border-r")}>
        <div className="eyebrow text-warning">{n === 1 ? "Talk 1 · your thoughts on the bull and bear cases" : "Talk 2 · your assistant"}</div>
        {n === 2 && <p className="-mt-1.5 text-[11.5px] text-muted">Ask, or tell it what to change. It answers and edits with Claude Haiku 5.5, searches the news when it needs new facts, and calls Claude Sonnet 5.5 if an edit fails the number check twice.</p>}
        {msgs.map((m, i) => (
          <div key={i} className={cn("max-w-[94%] rounded-xl px-3 py-2 text-[13px] leading-relaxed text-text-2",
            m.role === "user" ? "self-end rounded-br-sm bg-surface-3" : "self-start rounded-bl-sm border border-border bg-surface-2")}>
            {m.role === "agent" && <div className="mb-0.5 text-[11px] font-bold text-muted">{m.to === "ARC" ? "ARC" : `@${m.to}`}</div>}
            {m.text}<Chips ids={m.fact_ids} facts={idea.facts} />
            {m.role === "agent" && (m.trail?.length ?? 0) > 0 && (
              <div className="mt-1.5 flex flex-col gap-0.5">{m.trail.map((t, k) => <Step key={k} line={t} />)}</div>
            )}
            {m.role === "agent" && n === 1 && m.decision && (
              <div className={cn("mt-1.5 block w-fit rounded-full px-2 py-0.5 text-[11px] font-semibold",
                m.action === "research" ? "bg-warning-soft text-warning" : "bg-surface-3 text-muted")}>
                {decisionLabel(m)}
              </div>
            )}
          </div>
        ))}
        {working && (
          <div className="self-start rounded-xl border border-dashed border-warning/60 bg-warning-soft/50 px-3 py-2 text-[12.5px] font-semibold text-warning">
            <span className="mr-1.5 inline-block h-2.5 w-2.5 animate-spin rounded-full border-2 border-warning border-r-transparent align-[-1px]" />
            {idea.job?.message || "Starting…"}
          </div>
        )}
        {n === 1 && (
          <div className="text-[11px] text-muted">Talking to {["ARC", "Bull", "Bear", "Moderator"].map((w) => (
            <button key={w} onClick={() => setTo(w)} className={cn("ml-1 rounded-full border px-2 py-0.5 font-semibold",
              to === w ? "border-muted-2 bg-surface-3 text-text" : "border-border-strong text-text-2")}>{w === "ARC" ? w : `@${w}`}</button>))}</div>
        )}
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} disabled={busy}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder={n === 1 ? "Your thoughts, or a question…" : working ? "Working on your last message…" : "Ask, or tell me what to change…"}
          className="w-full rounded-xl border border-border-strong bg-surface-2 px-3 py-2 text-sm outline-none focus:border-accent disabled:opacity-60" />
        {error && <div className="text-xs text-danger">{error}</div>}
        {waiting && <div className="text-xs text-muted">{n === 1 ? "Thinking…" : "Sending…"}</div>}
        {n === 2 && <div className="flex justify-between text-[11.5px] text-muted"><span>One message at a time · no rounds</span><span>${idea.cost_usd.toFixed(2)} of $5 spent</span></div>}
      </div>
      {n === 1 && onSend && (
        <div className="p-4"><div className="eyebrow">Going to research</div>
          <p className="mt-0.5 text-xs text-muted">After each message OpenAI's Decisions API answers yes or no: yes adds it here. Remove anything you don't want.</p>
          <SendBar items={items} remove={remove} onSend={onSend} label={sendLabel ?? "Send to research"} busy={busy} />
          <p className="mt-2 text-[11.5px] text-muted">Your claims are never used as facts. A desk has to find a source first.</p></div>
      )}
    </div>
  );
}

// ponytail: desk cards fill in when the research step saves them, not after every search; save DeskRun progress
// from desks.run through store.edit if live counts turn out to matter.
export function Research({ idea }: { idea: Idea }) {
  const rnd = idea.rounds.find((r) => r.n === idea.round);
  const briefs = rnd?.briefs ?? [];
  const recent = [...idea.facts].reverse().filter((f) => /^(N|T)/.test(f.id)).slice(0, 12);
  if (!briefs.length) return <div className="rounded-2xl border border-border bg-surface p-6 text-sm text-muted">The orchestrator (gpt-6-sol) is writing the desks' briefs…</div>;
  return (
    <>
      <div className="grid gap-3 md:grid-cols-3">
        {briefs.map((b) => {
          const run = rnd?.desks.find((d) => d.desk === b.desk);
          const tech = b.desk === "technical";
          const stats: [string | number, string][] = run
            ? [[run.calls, tech ? "tool calls" : "searches"], [run.report?.findings.length ?? 0, "findings"], [tech ? "code" : run.domains.length, tech ? "numbers" : "outlets"]]
            : [];
          return (
            <div key={b.desk} className="rounded-2xl border border-border bg-surface p-4">
              <div className="flex items-center gap-2">
                <span className={cn("rounded-lg px-2 py-1 text-xs font-bold", tech ? TECH : NEWS)}>{tech ? "Technical" : "News"}</span>
                <b className="text-sm">{b.title}</b>
                <span className="ml-auto text-[11px] font-semibold text-muted">{run ? (run.error ? "failed" : "done") : "running"}</span>
              </div>
              <p className="my-2 text-[12.5px] text-muted">{b.brief}</p>
              {run && <div className="grid grid-cols-3 gap-1.5 text-center">{stats.map(([v, l]) => (
                <div key={l} className="rounded-lg bg-surface-2 py-1.5"><b className="block font-serif text-lg">{v}</b><span className="text-[10px] uppercase tracking-wide text-muted">{l}</span></div>))}</div>}
              {run && !tech && <div className="mt-2 flex flex-wrap gap-1">
                {run.domains.slice(0, 6).map((d) => <span key={d} className="rounded bg-surface-3 px-1.5 text-[11px]">{d}</span>)}
                {run.domains.length > 6 && <span className="text-[11px] text-muted">+{run.domains.length - 6}</span>}</div>}
              {run?.error && <p className="mt-2 text-xs text-danger">{run.error}</p>}
            </div>
          );
        })}
      </div>
      {recent.length > 0 && (
        <div className="rounded-2xl border border-border bg-surface">
          <div className="eyebrow px-4 pt-3">Facts from the desks</div>
          <table className="w-full text-[13px]"><tbody>{recent.map((f) => (
            <tr key={f.id} className="border-t border-border first:border-0">
              <td className="px-3 py-2 align-top"><FactChip id={f.id} facts={idea.facts} /></td>
              <td className="py-2 text-text-2">{f.text}</td>
              <td className="whitespace-nowrap px-3 py-2 text-xs text-muted">{f.source_title}</td></tr>))}</tbody></table>
        </div>
      )}
    </>
  );
}

export function ChartPicker({ idea, onIdea, busy }: { idea: Idea; onIdea: (i: Idea) => void; busy: boolean }) {
  const rnd = idea.rounds.find((r) => r.n === idea.round);
  const options = rnd?.options ?? [];
  const [picks, setPicks] = useState<Record<string, string>>(() =>
    Object.fromEntries(SECTIONS.map((s) => [s, options.find((o) => o.spec.section === s && o.file && o.spec.agent_pick)?.id ?? ""])));
  const [error, setError] = useState<string | null>(null);
  const [more, setMore] = useState<string | null>(null);
  const chosen = SECTIONS.map((s) => options.find((o) => o.id === picks[s])).filter(Boolean) as Option[];
  const forms = new Set(chosen.map((o) => o.spec.form)).size;
  const plain = chosen.filter((o) => PLAIN.has(o.spec.form)).length;
  const ok = chosen.length === SECTIONS.length && forms >= 6 && plain <= 2;
  const another = (s: string) => {
    setMore(s);
    trade.another(idea.id, s).then(() => trade.get(idea.id)).then(onIdea)
      .catch((e) => setError(String(e.message ?? e))).finally(() => setMore(null));
  };
  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-border bg-surface">
        {SECTIONS.map((s) => (
          <div key={s} className="grid gap-3 border-t border-border p-4 first:border-0 md:grid-cols-[200px_1fr]">
            <div><b className="text-[13.5px]">{SECTION_LABEL[s]}</b>
              {s === "intro" && <span className="ml-1 rounded-full bg-accent-soft px-1.5 text-[10px] font-bold text-accent">cover</span>}
              <button disabled={busy || more !== null} onClick={() => another(s)}
                className="mt-2 block rounded-full border border-dashed border-border-strong px-2.5 py-0.5 text-[11.5px] text-text-2">{more === s ? "Drawing…" : "+ Another idea"}</button></div>
            <div className="grid gap-2.5 sm:grid-cols-3">
              {options.filter((o) => o.spec.section === s && o.file).map((o) => (
                <label key={o.id} className={cn("relative cursor-pointer rounded-xl border-2 bg-surface-2 p-1.5", picks[s] === o.id ? "border-accent" : "border-border hover:border-border-strong")}>
                  <img src={trade.chartUrl(idea.id, o.file!)} alt={o.spec.title} className="aspect-[6.4/3.9] w-full rounded-lg bg-white object-cover" />
                  <input type="radio" name={s} checked={picks[s] === o.id} onChange={() => setPicks((p) => ({ ...p, [s]: o.id }))} className="mr-1.5 mt-1.5 align-middle accent-accent" />
                  <span className={cn("mt-1.5 inline-block rounded-full px-2 text-[10.5px] font-bold", TECH)}>{o.spec.form.replace("_", " ")}</span>
                  {o.spec.agent_pick && <span className="ml-1 text-[10.5px] font-bold text-warning">★ agent's pick</span>}
                  <span className="mt-0.5 block text-[11.5px] text-muted">{o.spec.why}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="sticky bottom-0 flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-surface px-4 py-3">
        <b>{chosen.length} of {SECTIONS.length} sections</b>
        <span className={cn("text-xs", plain > 2 || forms < 6 ? "text-warning" : "text-muted")}>{forms} different forms · {plain} plain line/bar (need 6+ forms, at most 2 plain)</span>
        {error && <span className="text-xs text-danger">{error}</span>}
        <button disabled={!ok || busy} onClick={() => trade.choose(idea.id, picks).then(onIdea).catch((e) => setError(String(e.message ?? e)))}
          className="ml-auto whitespace-nowrap rounded-full bg-accent px-4 py-2 text-[13px] font-semibold text-on-accent disabled:opacity-40">Write the draft →</button>
      </div>
    </div>
  );
}

// ponytail: white with black text on purpose: this previews Substack's own page, not the site's theme
export function Draft({ idea }: { idea: Idea }) {
  const r = idea.report;
  if (!r) return null;
  const picked = idea.rounds.find((x) => x.n === idea.round)?.options.filter((o) => o.chosen) ?? [];
  const chart = (section: string) => {
    const o = picked.find((c) => c.spec.section === section);
    return o?.file ? <img src={trade.chartUrl(idea.id, o.file)} alt={o.spec.title} className="my-3 w-full rounded-lg border border-black/10" /> : null;
  };
  const outline = [["intro", "Introduction"], ...r.sections.map((s) => [s.key, SECTION_LABEL[s.key]]), ["watch", "What to watch"]];
  const jump = (k: string) => document.getElementById(`draft-${k}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const para = "my-2 font-serif text-base leading-relaxed";
  const head = "scroll-mt-4 border-t border-black/10 pt-4 font-serif text-xl font-bold";
  // the editor marks emphasis as **bold**, which Substack renders; show it the same way here
  const rich = (t: string) => t.split(/\*\*(.+?)\*\*/g).map((x, i) => (i % 2 ? <b key={i}>{x}</b> : x));
  return (
    <div className="overflow-hidden rounded-2xl bg-white text-black/90">
      <div className="flex justify-between border-b border-black/10 px-4 py-2.5 text-xs text-black/50">
        <span>archresearch.substack.com · draft, not published</span>
        {idea.substack && <a href={idea.substack.url} target="_blank" rel="noreferrer" className="font-semibold text-accent">Open in Substack ↗</a>}
      </div>
      <div className="px-6 py-5">
        <div className="text-[11px] font-bold uppercase tracking-wider text-accent">ARC Special Topics</div>
        <h3 className="mt-1 font-serif text-[26px] font-bold leading-tight">{r.title}</h3>
        <p className="mb-3 text-[13.5px] text-black/55">{r.subtitle}</p>
        <div className="mb-4 flex flex-wrap gap-1.5">{outline.map(([k, x]) => (
          <button key={k} onClick={() => jump(k)} className="rounded-full bg-black/5 px-2 py-0.5 text-[11.5px] text-black/70 hover:bg-accent/15 hover:text-accent">{x}</button>
        ))}</div>
        <div id="draft-intro" className="scroll-mt-4 text-[11px] font-bold uppercase tracking-wider text-black/50">Introduction</div>
        {r.introduction.map((p, i) => <p key={i} className={para}>{rich(p)}</p>)}
        <div className="mt-3 text-[11px] font-bold uppercase tracking-wider text-black/50">Key takeaways</div>
        <ul className="list-disc pl-5 text-sm">{r.takeaways.map((t, i) => <li key={i} className="my-1">{rich(t)}</li>)}</ul>
        {chart("intro")}
        {r.sections.map((s) => (
          <section key={s.key} className="mt-5">
            <h4 id={`draft-${s.key}`} className={head}>{s.heading}</h4>
            {chart(s.key)}
            {s.paragraphs.map((p, i) => <p key={i} className={para}>{rich(p)}</p>)}
          </section>
        ))}
        <section className="mt-5">
          <h4 id="draft-watch" className={head}>What to watch</h4>
          {chart("watch")}
          <p className={para}>{rich(r.what_to_watch)}</p>
        </section>
        {r.changes.length > 0 && (
          <div className="mt-3 rounded-lg bg-black/5 p-3 text-xs"><b>What changed from your Substack edits:</b>
            <ul className="list-disc pl-4">{r.changes.map((c, i) => <li key={i}>{c}</li>)}</ul></div>
        )}
      </div>
    </div>
  );
}

export function Checks({ idea }: { idea: Idea }) {
  const rnd = idea.rounds.find((x) => x.n === idea.round);
  const outlets = new Set(idea.facts.filter((f) => f.provenance === "reported" && f.source_url).map((f) => {
    try { return new URL(f.source_url).hostname.replace(/^www\./, ""); } catch { return f.source_url; }
  }));
  const rows = [
    "Number check passed: every figure is matched to a fact",
    `${rnd?.options.filter((o) => o.chosen).length ?? 0} charts, one per section, as you picked them`,
    `Sources from ${outlets.size} outlets, listed at the end`,
    "Special Topics section · you hit Publish",
  ];
  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-3">
      <div className="eyebrow mb-1">Checks</div>
      {rows.map((t) => (
        <div key={t} className="flex items-center gap-2.5 border-t border-border py-2 text-[13.5px] text-text-2 first-of-type:border-0">
          <span className="grid h-5 w-5 place-items-center rounded-full bg-accent-soft text-[11px] text-accent">✓</span>{t}</div>
      ))}
    </div>
  );
}
