import { useEffect, useState } from "react";
import { X } from "lucide-react";
import type { DailyRecordV2, Exhibit } from "@/api/endpoints";
import { cn } from "@/lib/cn";

// Same path in dev (vite proxies /api) and on the static site (export_snapshot copies the PNGs).
// ?v= busts the browser cache when a day's note is regenerated (file names repeat: exhibit_N.png).
const chartUrl = (rec: DailyRecordV2, file: string) =>
  `/api/update/${rec.date}/charts/${file}?v=${encodeURIComponent(rec.generated_at)}`;
const TAG: Record<string, string> = { macro: "MACRO", news: "NEWS", alt: "ALT", ai: "AI" };
const LONG_DATE = new Intl.DateTimeFormat("en-GB", {
  weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
});

/** A chart opened over the page at full size; ✕, Esc or a click outside closes it. */
function ExhibitViewer({ src, ex, onClose }: { src: string; ex: Exhibit; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div role="dialog" aria-modal="true" aria-label={ex.title} onClick={onClose}
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 md:p-10">
      <div className="relative bg-white rounded-lg shadow-card-hover max-w-6xl w-full" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} aria-label="Close chart"
          className="absolute -top-3 -right-3 h-8 w-8 rounded-full bg-white border border-border shadow-card flex items-center justify-center hover:text-accent">
          <X className="h-4 w-4" />
        </button>
        <img src={src} alt={`${ex.title}. ${ex.subtitle}`} className="w-full h-auto max-h-[85vh] object-contain rounded-lg" />
      </div>
    </div>
  );
}

/** The v2 Daily Update: a sell-side style research note (approved mockup P1). */
export function MorningNote({ rec }: { rec: DailyRecordV2 }) {
  const { note } = rec;
  const findings = Object.fromEntries(rec.findings.map((f) => [f.id, f]));
  const exhibits = Object.fromEntries(rec.exhibits.map((e) => [e.finding_id, e]));
  const items = [...note.items].sort((a, b) => a.rank - b.rank);
  const [open, setOpen] = useState<Exhibit | null>(null);
  return (
    <article className="bg-white border border-border shadow-card px-5 py-6 md:px-11 md:py-9">
      <div className="flex justify-between items-end gap-3 border-b-[3px] border-accent pb-2.5">
        <div className="text-[13px] font-bold tracking-[0.16em] uppercase text-accent">ARC Research · Morning Note</div>
        <div className="text-xs text-muted text-right leading-[18px]">
          {LONG_DATE.format(new Date(`${rec.date}T00:00:00Z`))}
          <br />
          {rec.backfilled ? `Rebuilt ${rec.generated_at.slice(0, 10)}` : `Published ${rec.generated_at.slice(11, 16)}`}
        </div>
      </div>
      <div className="flex gap-4 text-[11px] text-muted border-b border-border py-1.5 uppercase tracking-wider">
        <span>Macro</span><span>News</span><span>Alt data</span>
        {rec.findings.some((f) => f.agent === "ai") && <span>AI &amp; chips</span>}
        <span className="ml-auto">{items.length} items · {rec.exhibits.length} exhibits</span>
      </div>
      <h2 className="font-serif font-bold text-[24px] md:text-[28px] leading-tight mt-5 mb-3.5">{note.headline}</h2>
      <div className="bg-surface-2 border-l-[3px] border-accent px-4 py-3 mb-6">
        <div className="text-[11px] font-bold tracking-[0.1em] uppercase text-accent">Key takeaways</div>
        <ul className="mt-1.5 pl-[18px] list-disc text-[13.5px] text-text-2 space-y-1">
          {note.takeaways.map((t) => <li key={t}>{t}</li>)}
        </ul>
      </div>
      {items.map((it) => {
        const ex = it.chart ? exhibits[it.chart] : undefined;
        const lead = findings[it.finding_ids[0]];
        const sources = it.finding_ids.map((id) => findings[id]).filter(Boolean);
        return (
          <section key={it.rank} className={cn("grid gap-7 py-5 border-t border-border", ex && "md:grid-cols-[1fr_420px]")}>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[11px] font-bold text-muted tracking-[0.1em]">
                {String(it.rank).padStart(2, "0")}
                {lead && (
                  <span className={cn("text-[10px] px-1.5 border rounded-sm",
                    lead.agent === "ai" ? "border-accent text-accent bg-accent-soft" : "border-border-strong text-text-2")}>{TAG[lead.agent]}</span>
                )}
              </div>
              <h3 className="font-serif font-bold text-[17px] leading-6 mt-1.5 mb-1.5">{it.title}</h3>
              <p className="text-[13.5px] leading-[22px] text-text-2">{it.body}</p>
              <div className="text-[11px] text-muted mt-1.5">
                {sources.map((f, i) => (
                  <span key={f.id}>
                    {i > 0 && " · "}
                    <a href={f.source_url} target="_blank" rel="noreferrer" className="hover:text-accent">{f.source_title}</a>
                  </span>
                ))}
              </div>
            </div>
            {ex && (
              <button type="button" onClick={() => setOpen(ex)} title="Open full size"
                className="block w-full border-t-2 border-text pt-1.5 cursor-zoom-in hover:opacity-90">
                <img src={chartUrl(rec, ex.file)} alt={`${ex.title}. ${ex.subtitle}`} className="w-full" loading="lazy" />
              </button>
            )}
          </section>
        );
      })}
      <div className="text-[10.5px] text-muted border-t border-border mt-2 pt-3 leading-4">
        Written by ARC Research's Daily Update agents (Macro, News, Alt{rec.findings.some((f) => f.agent === "ai") && ", AI analyst"}) and checked by a number guard: every figure
        above appears in the cited source data. Not investment advice.
        {rec.backfilled && <> Rebuilt on {rec.generated_at.slice(0, 10)} with the multi-agent desk, using data as of {rec.date}; news and X were searched for that date.</>}
        {rec.data_gaps.length > 0 && <> Sources unavailable: {rec.data_gaps.join("; ")}.</>}
      </div>
      {open && <ExhibitViewer src={chartUrl(rec, open.file)} ex={open} onClose={() => setOpen(null)} />}
    </article>
  );
}
