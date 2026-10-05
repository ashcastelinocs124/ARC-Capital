import { useEffect, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { useSectorSentiment } from "@/hooks/useSectorSentiment";
import type { SectorExplanation, SectorScore, SectorSentimentSnapshot, SectorStockRow } from "@/api/types";
import {
  CardHead, ExpandableCard, Headline, HowItWorks, Measures, Panel, StatCell, StatGrid, StatusBadge, Toggles, ago,
} from "@/components/modelCard";

// Sector Sentiment tool on the Models page, ported from Arc-Investment-Research/arc-dashboard. Positive divergence =
// price ahead of fundamentals (red), negative = fundamentals nobody is buying (green).

const fmt = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;

const cap = (v: number) => (v >= 1e12 ? `$${(v / 1e12).toFixed(1)}T` : `$${(v / 1e9).toFixed(0)}B`);

const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "text-danger" : "text-success");


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


const FRESH_HOURS = 24;
const count = (n: number) => `${n} sector${n === 1 ? "" : "s"}`;
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(0)}%`);
const KIND = "Technical − fundamental divergence · 11 GICS sectors, top 10 stocks each";

const HOW: { short: string; steps: ReactNode[] } = {
  short:
    "Scores each sector's top 10 stocks on technicals and on fundamentals; the gap between the two shows where price has run ahead of the business, or fallen behind it.",
  steps: [
    <><b>Technical score:</b> RSI-14, MACD histogram, price vs 50- and 200-day averages and 3-month return. Each metric is z-scored across all stocks, clipped at ±3σ, scaled to −1…+1 and averaged.</>,
    <><b>Fundamental score:</b> revenue growth, earnings growth and P/E relative to the sector median (cheaper scores higher), scored the same way.</>,
    <><b>Divergence</b> = technical − fundamental per stock, then cap-weighted across the sector's top 10.</>,
    <><b>Labels:</b> ≥ +0.30 euphoric (price ahead of fundamentals), ≤ −0.30 fearful (fundamentals nobody is buying), otherwise fair.</>,
    <><b>Explainer:</b> code works out whether a reading is sector-wide or driven by one stock; an LLM writes the prose, which describes and does not recommend.</>,
  ],
};

function Summary({ snap, expanded, onToggle }: { snap: SectorSentimentSnapshot; expanded: boolean; onToggle: () => void }) {
  const sectors = snap.sectors;
  // headline = the sector furthest from fair, either direction
  const top = sectors.reduce((a, b) => (Math.abs(b.divergence) > Math.abs(a.divergence) ? b : a), sectors[0]);
  const lowest = sectors.reduce((a, b) => (b.divergence < a.divergence ? b : a), sectors[0]);
  const fresh = (Date.now() - new Date(snap.as_of).getTime()) / 3_600_000 <= FRESH_HOURS;
  const e = top?.explanation;
  return (
    <>
      <CardHead
        name="Sector Sentiment"
        kind={KIND}
        badge={<StatusBadge status={fresh ? "fresh" : "stale"} text={`${fresh ? "Fresh" : "Stale"} · ${ago(snap.as_of)}`} />}
        expanded={expanded}
        onCollapse={onToggle}
      />
      {top && (
        <Headline
          value={`${top.divergence >= 0 ? "▲" : "▼"} ${fmt(top.divergence)}`}
          label={`${top.sector} — most stretched · ${top.label}`}
          tone={top.divergence >= 0 ? "danger" : "success"}
          fill={(Math.abs(top.divergence) / 0.5) * 100}
        />
      )}
      <StatGrid>
        <StatCell label="Euphoric (≥ +0.30)" value={count(sectors.filter((s) => s.label === "euphoric").length)} />
        <StatCell label="Fearful (≤ −0.30)" value={count(sectors.filter((s) => s.label === "fearful").length)} />
        {lowest && <StatCell label="Most negative" value={`${lowest.sector} ${fmt(lowest.divergence)}`} />}
        <StatCell label="Stocks scored" value={String(snap.stocks.length)} />
        <StatCell
          label="As of"
          value={new Date(snap.as_of).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
          warn={!fresh}
        />
        {e && <StatCell label={`Breadth (${top.sector})`} value={`${e.n_agree}/${e.n_total} same sign`} />}
      </StatGrid>
      <HowItWorks short={HOW.short} steps={HOW.steps} expanded={expanded} />
      <Measures
        question="Where price has run ahead of fundamentals (red) or fundamentals nobody is buying (green)."
        output="divergence per sector, −1 to +1; describes, does not recommend"
      />
    </>
  );
}

function SectorRows({ sectors, onOpen }: { sectors: SectorScore[]; onOpen: (s: string) => void }) {
  return (
    <>
      <table className="w-full text-xs">
        <thead className="text-muted">
          <tr>
            <th className="text-left py-1 font-medium">Sector</th>
            <th className="text-right font-medium">Tech</th>
            <th className="text-right font-medium">Fund</th>
            <th className="text-right font-medium">Divergence</th>
          </tr>
        </thead>
        <tbody>
          {sectors.map((s) => (
            <tr key={s.sector} data-stop onClick={() => onOpen(s.sector)} className="border-t border-border cursor-pointer hover:bg-surface-2">
              <td className="py-1.5">{s.sector}</td>
              <td className="text-right font-mono">{fmt(s.tech_score)}</td>
              <td className="text-right font-mono">{fmt(s.fund_score)}</td>
              <td className="text-right"><DivergenceChip v={s.divergence} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="text-[11px] text-muted mt-1.5">Click a sector for its constituents and the explainer.</div>
    </>
  );
}

function Narrative({ snap }: { snap: SectorSentimentSnapshot }) {
  return (
    <>
      <p className="text-xs leading-relaxed text-text-2">{snap.narrative}</p>
      <p className="mt-1.5 text-[11px] text-muted">
        Sector Sentiment Narrative
        {snap.narrative_generated_at && ` · generated ${new Date(snap.narrative_generated_at).toLocaleString()}`} · describes, does not recommend
      </p>
    </>
  );
}

function SectorPicker({ sectors, value, onPick }: { sectors: SectorScore[]; value?: string; onPick: (s: string) => void }) {
  return (
    <select
      value={value}
      onChange={(ev) => onPick(ev.target.value)}
      aria-label="Sector"
      className="mb-1.5 rounded-lg border border-border-strong bg-surface px-2 py-1 text-xs font-semibold text-text"
    >
      {sectors.map((x) => (
        <option key={x.sector} value={x.sector}>{x.sector} ({fmt(x.divergence)})</option>
      ))}
    </select>
  );
}

// full = every metric column (expanded view); otherwise the narrow card version
function Stocks({ rows, full }: { rows: SectorStockRow[]; full: boolean }) {
  const cols: [string, (r: SectorStockRow) => string][] = full
    ? [
        ["Cap", (r) => cap(r.market_cap)],
        ["RSI 14", (r) => r.rsi14?.toFixed(0) ?? "—"],
        ["vs SMA200", (r) => pct(r.vs_sma200)],
        ["3-mo ret", (r) => pct(r.ret_3m)],
        ["Rev YoY", (r) => pct(r.rev_yoy)],
        ["P/E vs sector", (r) => (r.pe_rel != null ? `${r.pe_rel.toFixed(1)}×` : "—")],
        ["Tech", (r) => fmt(r.tech_score)],
        ["Fund", (r) => fmt(r.fund_score)],
      ]
    : [
        ["Cap", (r) => cap(r.market_cap)],
        ["Tech", (r) => fmt(r.tech_score)],
        ["Fund", (r) => fmt(r.fund_score)],
      ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-muted">
          <tr>
            <th className="text-left py-1 font-medium">Ticker</th>
            {cols.map(([h]) => <th key={h} className="text-right font-medium px-1">{h}</th>)}
            <th className="text-right font-medium">Div</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className="border-t border-border" title={r.name}>
              <td className="py-1.5 font-mono font-semibold">
                {r.symbol}
                {full && <span className="ml-1.5 font-sans font-normal text-muted">{r.name}</span>}
              </td>
              {cols.map(([h, get]) => <td key={h} className="text-right font-mono px-1">{get(r)}</td>)}
              <td className="text-right"><DivergenceChip v={r.divergence} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SectorSentimentSection({ expanded, onToggle }: { expanded: boolean; onToggle: () => void }) {
  const { data: snap, isLoading } = useSectorSentiment();
  const [open, setOpen] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);

  if (!snap) {
    return (
      <div className="card p-5">
        <CardHead name="Sector Sentiment" kind={KIND} badge={<StatusBadge status="missing" text="No snapshot" />} />
        <div className="text-center text-sm text-muted py-6">
          {isLoading ? "Loading…" : <>No snapshot yet — it builds in the background when <code className="font-mono">ckm serve</code> starts.</>}
        </div>
      </div>
    );
  }

  const sectors = snap.sectors;
  const openSector = sectors.find((s) => s.sector === open) ?? null;
  const tableSector = sectors.find((s) => s.sector === picked) ?? sectors[0];
  const rows = snap.stocks.filter((r) => r.sector === tableSector?.sector).sort((a, b) => b.market_cap - a.market_cap);
  const picker = <SectorPicker sectors={sectors} value={tableSector?.sector} onPick={setPicked} />;

  return (
    <>
      <ExpandableCard
        expanded={expanded}
        onToggle={onToggle}
        collapsed={
          <>
            <Summary snap={snap} expanded={false} onToggle={onToggle} />
            <Toggles
              tabs={[
                { key: "sectors", label: `Sectors (${sectors.length})`, render: () => <SectorRows sectors={sectors} onOpen={setOpen} /> },
                ...(snap.narrative ? [{ key: "narrative", label: "Narrative", render: () => <Narrative snap={snap} /> }] : []),
                { key: "stocks", label: `Stocks (${snap.stocks.length})`, render: () => <>{picker}<Stocks rows={rows} full={false} /></> },
              ]}
            />
          </>
        }
        full={{
          left: <Summary snap={snap} expanded onToggle={onToggle} />,
          right: (
            <div className="grid xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3.5 items-start">
              <Panel title={`Sectors (${sectors.length})`}><SectorRows sectors={sectors} onOpen={setOpen} /></Panel>
              <div className="space-y-3.5 min-w-0">
                {snap.narrative && <Panel title="Narrative"><Narrative snap={snap} /></Panel>}
                <Panel title={`Stocks · top ${rows.length} by market cap`}>{picker}<Stocks rows={rows} full /></Panel>
              </div>
            </div>
          ),
        }}
      />
      {openSector && <SectorDrawer s={openSector} onClose={() => setOpen(null)} />}
    </>
  );
}
