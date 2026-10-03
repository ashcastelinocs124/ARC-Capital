import { useEffect, useState } from "react";
import { Sparkles, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { useSectorSentiment } from "@/hooks/useSectorSentiment";
import type { SectorExplanation, SectorScore, SectorStockRow } from "@/api/types";

// Sector Sentiment tool on the Models page, ported from Arc-Investment-Research/arc-dashboard. Positive divergence =
// price ahead of fundamentals (red), negative = fundamentals nobody is buying (green).

const fmt = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;

const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(0)}%`;

const cap = (v: number) => (v >= 1e12 ? `$${(v / 1e12).toFixed(1)}T` : `$${(v / 1e9).toFixed(0)}B`);

const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "text-danger" : "text-success");

// Cap-weighted average over the rows that have the metric (weights renormalized).
const wavg = (rows: SectorStockRow[], get: (r: SectorStockRow) => number | null): number | null => {
  const xs = rows.filter((r) => get(r) != null && r.market_cap > 0);
  const total = xs.reduce((a, r) => a + r.market_cap, 0);
  return total > 0 ? xs.reduce((a, r) => a + get(r)! * r.market_cap, 0) / total : null;
};

function DivergenceChip({ v }: { v: number | null }) {
  if (v === null) return <span className="text-muted-2">—</span>;
  return (
    <span
      className={cn(
        "inline-block text-xs font-semibold px-1.5 py-0.5 rounded",
        v > 0 && "text-danger bg-danger-soft",
        v < 0 && "text-success bg-success-soft",
        v === 0 && "text-muted bg-surface-3",
      )}
    >
      {fmt(v)}
    </span>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted">
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full bg-danger" aria-hidden />
        positive — price running ahead of fundamentals (euphoric at ≥ +0.30)
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full bg-success" aria-hidden />
        negative — strong fundamentals nobody is buying (fearful at ≤ −0.30)
      </span>
    </div>
  );
}

function SectorTile({ s, onOpen }: { s: SectorScore; onOpen: (sector: string) => void }) {
  return (
    <button
      onClick={() => onOpen(s.sector)}
      aria-label={`${s.sector}: divergence ${fmt(s.divergence)}, ${s.label} — open breakdown`}
      className={cn(
        "text-left rounded-xl border p-3.5 shadow-card transition-shadow hover:shadow-card-hover",
        s.label === "euphoric" && "bg-danger-soft border-danger/40",
        s.label === "fearful" && "bg-success-soft border-success/40",
        s.label === "fair" && "bg-surface border-border",
      )}
    >
      <div className="text-sm font-semibold text-text">{s.sector}</div>
      <div className={cn("font-mono mt-1.5 text-lg font-semibold", tone(s.divergence))}>{fmt(s.divergence)}</div>
      <div className="mt-0.5 text-xs text-muted">
        {s.label}
        {s.zscore !== null && ` · z ${fmt(s.zscore, 1)}`}
      </div>
    </button>
  );
}

const VERDICT: Record<SectorExplanation["verdict"], { label: string; cls: string }> = {
  sector_wide: { label: "Sector-wide", cls: "bg-warning-soft text-warning border-warning/40" },
  stock_specific: { label: "Stock-specific", cls: "bg-accent-soft text-accent border-accent/40" },
  mixed: { label: "Mixed", cls: "bg-surface-3 text-muted border-border-strong" },
};

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2">
      <div className="text-xs text-muted">{k}</div>
      <div className="font-mono mt-0.5 text-sm font-semibold">{v}</div>
    </div>
  );
}

// Right-hand drawer: verdict + stats + contribution bars, all computed in Python.
function SectorDrawer({ s, onClose }: { s: SectorScore; onClose: () => void }) {
  const e = s.explanation;
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => ev.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const maxAbs = e ? Math.max(...e.contributions.map((c) => Math.abs(c.contribution)), 1e-9) : 0;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`${s.sector} breakdown`}>
      <div className="absolute inset-0 bg-black/30" onClick={onClose} aria-hidden />
      <div className="absolute inset-y-0 right-0 w-full max-w-[440px] overflow-y-auto border-l border-border bg-surface p-6">
        <div className="flex items-center gap-2.5">
          <span className="text-base font-semibold">{s.sector}</span>
          <span className={cn("font-mono text-base font-semibold", tone(s.divergence))}>{fmt(s.divergence)}</span>
          <span className="text-xs text-muted">{s.label}</span>
          {e && (
            <span className={cn("rounded-full border px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide", VERDICT[e.verdict].cls)}>
              {VERDICT[e.verdict].label}
            </span>
          )}
          <button onClick={onClose} aria-label="Close" className="ml-auto rounded-md p-1 text-muted hover:bg-surface-2 hover:text-text">
            <X className="h-4 w-4" />
          </button>
        </div>

        {e ? (
          <>
            <div className="mt-4 grid grid-cols-2 gap-2.5">
              <Stat k="stocks sharing sign" v={`${e.n_agree} / ${e.n_total}`} />
              <Stat k="largest contributor" v={`${e.top_symbol} · ${(e.top_share * 100).toFixed(0)}%`} />
              <Stat k="cap-wt vs equal-wt" v={`${fmt(s.divergence)} / ${fmt(e.equal_weight_divergence)}`} />
              <Stat k="drivers" v={e.drivers.join(" · ")} />
            </div>
            <div className="mt-4 text-xs uppercase tracking-wide text-muted">Contribution to sector divergence</div>
            <div className="mt-1.5 space-y-1">
              {e.contributions.map((c) => (
                <div key={c.symbol} className="grid grid-cols-[56px_1fr_64px] items-center gap-2.5 text-xs">
                  <span className="font-mono font-semibold">{c.symbol}</span>
                  <div className="h-1.5 rounded bg-surface-3">
                    <div
                      className={cn("h-1.5 rounded", c.contribution >= 0 ? "bg-danger" : "bg-success")}
                      style={{ width: `${(Math.abs(c.contribution) / maxAbs) * 100}%` }}
                    />
                  </div>
                  <span className="font-mono text-right text-muted">{fmt(c.contribution, 3)}</span>
                </div>
              ))}
            </div>
            <p className="mt-4 text-sm leading-relaxed text-text-2">
              {e.prose ?? <span className="text-muted">No agent read for this sector — the numbers above are computed from the snapshot.</span>}
            </p>
            <p className="mt-2 text-xs text-muted">
              Sector Explainer · verdict computed in code
              {e.generated_at && ` · prose generated ${new Date(e.generated_at).toLocaleString()}`} · describes, does not recommend
            </p>
          </>
        ) : (
          <p className="mt-4 text-sm text-muted">No breakdown in this snapshot yet.</p>
        )}
      </div>
    </div>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return <td className="px-2.5 py-1.5 text-right font-mono">{children}</td>;
}

function SectorTable({ s, rows }: { s: SectorScore; rows: SectorStockRow[] }) {
  const pe = wavg(rows, (r) => r.pe_rel);
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
      <div className="border-b border-border px-5 py-3">
        <span className="text-sm font-semibold">{s.sector} — top {rows.length} by market cap</span>
        <span className="ml-2.5 text-xs text-muted">cap-weighted {fmt(s.divergence)} · {s.label}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-[10px] uppercase tracking-wide text-muted">
              <th className="px-5 py-2 text-left font-medium">Symbol</th>
              {["Mkt cap", "RSI 14", "vs SMA200", "3-mo ret", "Rev YoY", "P/E vs sector", "Tech", "Fund"].map((h) => (
                <th key={h} className="px-2.5 py-2 text-right font-medium">{h}</th>
              ))}
              <th className="px-5 py-2 text-right font-medium">Divergence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol} className="border-b border-border/60">
                <td className="px-5 py-1.5">
                  <span className="font-semibold">{r.symbol}</span> <span className="text-muted">{r.name}</span>
                  {r.fundamentals_missing && <span className="text-muted-2"> · fundamentals unavailable</span>}
                </td>
                <Td>{cap(r.market_cap)}</Td>
                <Td>{r.rsi14?.toFixed(0) ?? "—"}</Td>
                <Td>{pct(r.vs_sma200)}</Td>
                <Td>{pct(r.ret_3m)}</Td>
                <Td>{pct(r.rev_yoy)}</Td>
                <Td>{r.pe_rel !== null ? `${r.pe_rel.toFixed(1)}×` : "—"}</Td>
                <Td>{fmt(r.tech_score)}</Td>
                <Td>{fmt(r.fund_score)}</Td>
                <td className="px-5 py-1.5 text-right"><DivergenceChip v={r.divergence} /></td>
              </tr>
            ))}
            <tr className="bg-surface-2 font-semibold">
              <td className="px-5 py-2">Average (cap-weighted)</td>
              <Td>{""}</Td>
              <Td>{wavg(rows, (r) => r.rsi14)?.toFixed(0) ?? "—"}</Td>
              <Td>{pct(wavg(rows, (r) => r.vs_sma200))}</Td>
              <Td>{pct(wavg(rows, (r) => r.ret_3m))}</Td>
              <Td>{pct(wavg(rows, (r) => r.rev_yoy))}</Td>
              <Td>{pe !== null ? `${pe.toFixed(1)}×` : "—"}</Td>
              <Td>{fmt(s.tech_score)}</Td>
              <Td>{fmt(s.fund_score)}</Td>
              <td className="px-5 py-2 text-right"><DivergenceChip v={s.divergence} /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function SectorSentimentSection() {
  const { data: snap, isLoading } = useSectorSentiment();
  const [open, setOpen] = useState<string | null>(null);
  const openSector = snap?.sectors.find((s) => s.sector === open) ?? null;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-text">Sector Sentiment</h2>
        <p className="text-xs text-muted mt-0.5">
          Divergence = technical score − fundamental score across each GICS sector's top 10 stocks.
          {snap && ` As of ${new Date(snap.as_of).toLocaleString()}.`}
        </p>
        <div className="mt-1.5"><Legend /></div>
      </div>

      {isLoading && <div className="text-sm text-muted">Loading…</div>}
      {!isLoading && !snap && (
        <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">
          No snapshot yet — it builds in the background when <code className="font-mono">ckm serve</code> starts
          (a minute or two), and this page updates itself.
        </div>
      )}
      {snap && (
        <>
          {snap.narrative && (
            <div className="flex gap-3 rounded-xl border border-border bg-surface px-5 py-4 shadow-card">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft">
                <Sparkles className="h-3.5 w-3.5 text-accent" aria-hidden />
              </div>
              <div>
                <p className="text-sm leading-relaxed text-text-2">{snap.narrative}</p>
                <p className="mt-1.5 text-xs text-muted">
                  Sector Sentiment Narrative
                  {snap.narrative_generated_at && ` · generated ${new Date(snap.narrative_generated_at).toLocaleString()}`}
                  {" "}· describes, does not recommend
                </p>
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4 xl:grid-cols-6">
            {snap.sectors.map((s) => <SectorTile key={s.sector} s={s} onOpen={setOpen} />)}
          </div>
          {openSector && <SectorDrawer s={openSector} onClose={() => setOpen(null)} />}
          {snap.sectors.map((s) => (
            <SectorTable
              key={s.sector}
              s={s}
              rows={snap.stocks.filter((r) => r.sector === s.sector).sort((a, b) => b.market_cap - a.market_cap)}
            />
          ))}
        </>
      )}
    </div>
  );
}
