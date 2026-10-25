import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, CornerDownLeft, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { useAgentCatalog } from "@/hooks/useAgentCatalog";
import { useOverview } from "@/components/admin/Overview";

type Hit = { key: string; label: string; hint: string; to: string; icon?: LucideIcon };
type SectionLike = { id: string; label: string; group: string; icon: LucideIcon };

/** ⌘K: jump to a section, an agent (opens it in Agents) or anything waiting or running (from the Overview). */
export default function CommandPalette({ sections, href, onClose }: {
  sections: SectionLike[]; href: (id: string) => string; onClose: () => void;
}) {
  const nav = useNavigate();
  const { data: catalog } = useAgentCatalog(true);
  const { data: ov } = useOverview();
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const back = useRef<Element | null>(document.activeElement);

  useEffect(() => {
    input.current?.focus();
    const was = back.current;
    return () => { (was as HTMLElement | null)?.focus?.(); }; // focus returns to where ⌘K was pressed
  }, []);

  const all = useMemo<Hit[]>(() => [
    ...sections.map((s) => ({ key: `s:${s.id}`, label: s.label, hint: s.group || "Section", to: href(s.id), icon: s.icon })),
    ...[...(ov?.needs_you ?? []), ...(ov?.running ?? [])].map((it, i) => ({
      key: `o:${i}`, label: it.title, hint: it.detail, to: it.href,
    })),
    ...(catalog?.agents ?? []).map((a) => ({
      key: `a:${a.id}`, label: a.name, hint: `Agent · ${a.group}`, to: `/admin/agents?agent=${encodeURIComponent(a.id)}`, icon: Bot,
    })),
  ], [sections, href, ov, catalog]);
  const hits = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (t ? all.filter((h) => `${h.label} ${h.hint}`.toLowerCase().includes(t)) : all.filter((h) => h.key.startsWith("s:") || h.key.startsWith("o:"))).slice(0, 12);
  }, [all, q]);

  const go = (h: Hit | undefined) => { if (h) { onClose(); nav(h.to); } };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((i) => Math.min(i + 1, hits.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); go(hits[hi]); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/45 px-4 pt-[12vh]" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label="Search the admin" className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface shadow-2xl">
        <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setHi(0); }} onKeyDown={onKey}
          role="combobox" aria-expanded="true" aria-controls="admin-palette-list" aria-label="Search sections, agents and jobs"
          aria-activedescendant={hits[hi] ? `pal-${hits[hi].key}` : undefined}
          placeholder="Jump to a section, an agent, or something waiting or running…"
          className="h-12 w-full border-b border-border-soft bg-transparent px-4 text-[15px] text-text outline-none placeholder:text-muted" />
        <ul id="admin-palette-list" role="listbox" className="max-h-[50vh] overflow-auto p-1.5">
          {hits.length === 0 && <li className="px-3 py-6 text-center text-[13px] text-muted">Nothing matches &ldquo;{q}&rdquo;.</li>}
          {hits.map((h, i) => (
            <li key={h.key} id={`pal-${h.key}`} role="option" aria-selected={i === hi}
              onMouseEnter={() => setHi(i)} onClick={() => go(h)}
              className={cn("flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-[13px]",
                i === hi ? "bg-surface-3 text-text" : "text-text-2")}>
              {h.icon ? <h.icon className="h-4 w-4 flex-none text-muted" aria-hidden="true" /> : <span className="h-4 w-4 flex-none" />}
              <span className="truncate">{h.label}</span>
              <span className="ml-auto max-w-[45%] truncate text-xs text-muted">{h.hint}</span>
              {i === hi && <CornerDownLeft className="h-3.5 w-3.5 flex-none text-muted" aria-hidden="true" />}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
