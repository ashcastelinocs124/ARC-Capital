import { useEffect, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useAdoptionCompanies, useAdoptionSummary, useAllAdoptionCompanies } from "@/hooks/useAdoption";
import type { AdoptionCell, AdoptionCompany, AdoptionSummary, Bucket } from "@/api/adoption";
import { cn } from "@/lib/cn";
import {
  CardHead, ExpandableCard, Headline, HowItWorks, Measures, Panel, StatCell, StatGrid, StatusBadge, Toggles, ago,
} from "@/components/modelCard";

const SECTORS = [
  "Information Technology", "Communication Services", "Consumer Discretionary", "Financials",
  "Health Care", "Industrials", "Consumer Staples", "Energy", "Utilities", "Materials", "Real Estate",
];
const CADENCE_DAYS = 15; // bi-weekly runs; older than this is stale

const f = (x: number | null | undefined, d = 1) => (x == null ? "—" : x.toFixed(d));
const signed = (x: number | null | undefined) => (x == null ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(1)}`);

function heat(v: number): React.CSSProperties {
  const t = Math.max(0, Math.min(1, (v - 25) / 55));
  return { background: `rgba(0,135,68,${(0.1 + t * 0.55).toFixed(2)})`, color: t > 0.62 ? "#fff" : undefined };
}

function Score({ cell }: { cell?: AdoptionCell }) {
  if (!cell || cell.ew == null) return <span className="text-muted-2">—</span>;
  return (
    <>
      <span
        className={cn(
          "inline-block min-w-[34px] text-center rounded px-1.5 font-mono font-semibold",
          cell.thin && "outline-dashed outline-1 outline-warning bg-warning-soft text-warning",
        )}
        style={cell.thin ? undefined : heat(cell.ew)}
      >
        {cell.ew.toFixed(0)}
      </span>
      <span className="ml-1 text-[10px] text-muted-2">n={cell.n}</span>
    </>
  );
}

function CompanyRows({ rows }: { rows: AdoptionCompany[] }) {
  if (rows.length === 0) return <div className="text-xs text-muted">No companies.</div>;
  return (
    <table className="w-full text-xs">
      <tbody>
        {rows.map((r) => (
          <tr key={r.ticker} className="border-t border-border first:border-0 align-top">
            <td className="py-1.5 pr-2 font-mono font-semibold">{r.ticker}</td>
            <td className="py-1.5 pr-3 font-mono text-right">{f(r.score, 0)}</td>
            <td className="py-1.5 text-muted">{r.claims[0] ? `"${r.claims[0].quote.slice(0, 90)}…"` : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Side drawer per sector, same shape as the Sector Sentiment drawer.
function AdoptionDrawer({ sector, onClose }: { sector: string; onClose: () => void }) {
  const large = useAdoptionCompanies(sector, "large");
  const small = useAdoptionCompanies(sector, "small");
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => ev.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const pick = (d: AdoptionCompany[] | undefined) => (Array.isArray(d) ? d : []);
  const block = (label: string, rows: AdoptionCompany[]) => (
    <div className="mt-4">
      <div className="text-xs uppercase tracking-wide text-muted mb-1">{label}</div>
      <table className="w-full text-xs">
        <thead className="text-muted">
          <tr>
            <th className="text-left py-1 font-medium">Ticker</th>
            <th className="text-right font-medium">Score</th>
            <th className="text-right font-medium">Talk</th>
            <th className="text-right font-medium">Hire</th>
            <th className="text-right font-medium">Spend</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticker} className="border-t border-border">
              <td className="py-1.5 font-mono font-semibold">{r.ticker}</td>
              <td className="text-right font-mono font-semibold">{f(r.score, 0)}</td>
              <td className="text-right font-mono">{f(r.s_talk, 0)}</td>
              <td className="text-right font-mono">{f(r.s_hire, 0)}</td>
              <td className="text-right font-mono">{f(r.s_spend, 0)}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={5} className="py-2 text-muted">No companies in this cell.</td></tr>
          )}
        </tbody>
      </table>
      {rows.filter((r) => r.claims[0]).map((r) => (
        <p key={r.ticker} className="mt-2 text-xs text-text-2">
          <span className="font-mono font-semibold">{r.ticker}</span> — "{r.claims[0].quote}"
        </p>
      ))}
    </div>
  );
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`${sector} adoption`}>
      <div className="absolute inset-0 bg-black/30" onClick={onClose} aria-hidden />
      <div className="absolute inset-y-0 right-0 w-full max-w-[440px] overflow-y-auto border-l border-border bg-surface p-6">
        <div className="flex items-center gap-2.5">
          <span className="text-base font-semibold">{sector}</span>
          <span className="text-xs text-muted">AI adoption by company</span>
          <button onClick={onClose} aria-label="Close" className="ml-auto rounded-md p-1 text-muted hover:bg-surface-2 hover:text-text">
            <X className="h-4 w-4" />
          </button>
        </div>
        {block("Large cap", pick(large.data))}
        {block("Small cap", pick(small.data))}
        <p className="mt-4 text-xs text-muted">Quotes are verbatim from the company's latest filing; claims not found in the filing are dropped.</p>
      </div>
    </div>
  );
}

function AllCompanies({ full }: { full: boolean }) {
  const { data } = useAllAdoptionCompanies();
  const rows = (Array.isArray(data) ? data : []).filter((r) => r.score != null);
  if (!full) return <div className="max-h-72 overflow-y-auto"><CompanyRows rows={rows} /></div>;
  return (
    <div className="max-h-96 overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="text-muted sticky top-0 bg-surface">
          <tr>
            <th className="text-left py-1 font-medium">Ticker</th>
            <th className="text-right font-medium px-1">Score</th>
            <th className="text-right font-medium px-1">Talk</th>
            <th className="text-right font-medium px-1">Hire</th>
            <th className="text-right font-medium px-1">Spend</th>
            <th className="text-left font-medium pl-2">Top verified claim</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticker} className="border-t border-border align-top">
              <td className="py-1.5 font-mono font-semibold">{r.ticker}</td>
              <td className="text-right font-mono font-semibold px-1">{f(r.score, 0)}</td>
              <td className="text-right font-mono px-1">{f(r.s_talk, 0)}</td>
              <td className="text-right font-mono px-1">{f(r.s_hire, 0)}</td>
              <td className="text-right font-mono px-1">{f(r.s_spend, 0)}</td>
              <td className="pl-2 py-1.5 text-muted">{r.claims[0] ? `"${r.claims[0].quote}"` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const KIND = "Research metric · Talk + Hire + Spend";

const HOW: { short: string; steps: ReactNode[] } = {
  short:
    "Scores each company 0–100 on how far it has adopted AI, from what its filings say, who it is hiring and what it spends, then rolls the scores up by sector and size.",
  steps: [
    <><b>Talk:</b> an LLM rates AI passages in the latest 10-K/10-Q as 1 pilot, 2 deployed or 3 revenue-linked; every quote must appear verbatim in the filing or it is dropped. Score = rated claims per 1,000 words.</>,
    <><b>Hire:</b> share of open roles that are AI/ML engineering, from Greenhouse/Lever job boards, averaged over the last 7 bi-weekly snapshots.</>,
    <><b>Spend:</b> capex + R&amp;D as a share of revenue, trailing twelve months.</>,
    <><b>Score:</b> each pillar is z-scored across all companies, clipped at ±3σ and mapped to 0–100 (average 50); a company needs at least 2 of the 3 pillars.</>,
    <><b>Roll-up:</b> equal-weighted (headline) and market-cap-weighted per sector and size bucket; cells with fewer than 5 companies are flagged thin.</>,
  ],
};

function Summary({ data, expanded, onToggle }: { data: AdoptionSummary; expanded: boolean; onToggle: () => void }) {
  const h = data.headline;
  const s = data.stats;
  const ageDays = (Date.now() - new Date(data.period!).getTime()) / 86_400_000;
  const nBucket = (b: Bucket) => data.cells.filter((c) => c.bucket === b).reduce((a, c) => a + c.n, 0);
  const hireOff = s != null && s.pillar_coverage.hire === 0;
  return (
    <>
      <CardHead
        name="AI Adoption Index"
        kind={s ? `${KIND} · ${s.n_companies} companies` : `${KIND} · ${nBucket("large")} large + ${nBucket("small")} small caps`}
        badge={
          <StatusBadge
            status={ageDays <= CADENCE_DAYS ? "fresh" : "stale"}
            text={`${ageDays <= CADENCE_DAYS ? "Fresh" : "Stale"} · ${ageDays < 1 ? "today" : ago(data.period!)}`}
          />
        }
        expanded={expanded}
        onCollapse={onToggle}
      />
      <Headline
        value={f(h.large_ew)}
        label="large caps, equal-weighted · universe avg = 50"
        tone={(h.large_ew ?? 0) >= 50 ? "success" : "danger"}
        fill={h.large_ew ?? 0}
      />
      <StatGrid>
        <StatCell label="Small caps (EW)" value={f(h.small_ew)} />
        <StatCell label="Size spread (small − large)" value={signed(h.spread)} />
        <StatCell label="Large-cap concentration" value={signed(h.large_concentration)} />
        {s && <StatCell label="Companies scored" value={`${s.n_scored} / ${s.n_companies}`} />}
        {s && <StatCell label="Verified claims" value={String(s.n_claims)} />}
        <StatCell label="Period" value={data.period!} warn={ageDays > CADENCE_DAYS} />
      </StatGrid>
      {hireOff && (
        <div className="mt-3 text-xs bg-warning-soft text-warning rounded-lg px-3 py-2">
          Hire pillar is off (no job_boards.csv yet), so companies are scored on Talk and Spend only.
        </div>
      )}
      <HowItWorks short={HOW.short} steps={HOW.steps} expanded={expanded} />
      <Measures
        question="How far companies have adopted AI, from filing language, AI/ML hiring and capex + R&D."
        output="0–100 score per company, rolled up by sector and size; research metric, not in the trading pipeline"
      />
    </>
  );
}

function SectorGrid({ data, onOpen }: { data: AdoptionSummary; onOpen: (s: string) => void }) {
  const cell = (sector: string, bucket: Bucket) => data.cells.find((c) => c.sector === sector && c.bucket === bucket);
  return (
    <>
      <table className="w-full text-xs">
        <thead className="text-muted">
          <tr>
            <th className="text-left py-1 font-medium">Sector</th>
            <th className="text-right font-medium">Large</th>
            <th className="text-right font-medium">Small</th>
          </tr>
        </thead>
        <tbody>
          {SECTORS.map((sec) => (
            <tr key={sec} data-stop onClick={() => onOpen(sec)} className="border-t border-border cursor-pointer hover:bg-surface-2">
              <td className="py-1.5">{sec}</td>
              <td className="text-right"><Score cell={cell(sec, "large")} /></td>
              <td className="text-right"><Score cell={cell(sec, "small")} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="text-[11px] text-muted mt-1.5">
        Dashed amber = thin cell (n &lt; 5), indicative only. Click a sector for its companies and source quotes.
      </div>
    </>
  );
}

function Trend({ data }: { data: AdoptionSummary }) {
  const rows = data.series.map((p) => ({ period: p.period, Large: p.large_ew, Small: p.small_ew }));
  if (rows.length < 2) return <div className="text-xs text-muted">A trend needs at least two periods; the next run adds the line.</div>;
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={rows}>
        <CartesianGrid stroke="#ececef" />
        <XAxis dataKey="period" tick={{ fontSize: 10 }} />
        <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10 }} width={32} />
        <Tooltip />
        <Legend />
        <Line type="monotone" dataKey="Large" stroke="#008744" strokeWidth={2} dot={false} connectNulls />
        <Line type="monotone" dataKey="Small" stroke="#71717a" strokeWidth={2} strokeDasharray="4 3" dot={false} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function AdoptionSection({ expanded, onToggle }: { expanded: boolean; onToggle: () => void }) {
  const { data, isLoading } = useAdoptionSummary();
  const [open, setOpen] = useState<string | null>(null);

  if (isLoading || !data || Array.isArray(data) || data.period == null) {
    return (
      <div className="card p-5">
        <CardHead name="AI Adoption Index" kind={KIND} badge={<StatusBadge status="missing" text="No data" />} />
        <div className="text-center text-sm text-muted py-6">
          {isLoading ? "Loading…" : <>No adoption data yet. Run <code className="font-mono">ckm adoption run</code>.</>}
        </div>
      </div>
    );
  }

  const s = data.stats;
  return (
    <>
      <ExpandableCard
        expanded={expanded}
        onToggle={onToggle}
        collapsed={
          <>
            <Summary data={data} expanded={false} onToggle={onToggle} />
            <Toggles
              tabs={[
                { key: "sectors", label: `Sectors (${SECTORS.length})`, render: () => <SectorGrid data={data} onOpen={setOpen} /> },
                { key: "companies", label: `Companies${s ? ` (${s.n_scored})` : ""}`, render: () => <AllCompanies full={false} /> },
                { key: "trend", label: "Trend", render: () => <Trend data={data} /> },
              ]}
            />
          </>
        }
        full={{
          left: <Summary data={data} expanded onToggle={onToggle} />,
          right: (
            <div className="grid xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3.5 items-start">
              <Panel title={`Sectors (${SECTORS.length})`}><SectorGrid data={data} onOpen={setOpen} /></Panel>
              <div className="space-y-3.5 min-w-0">
                <Panel title={`Companies${s ? ` (${s.n_scored})` : ""} · top verified claim`}><AllCompanies full /></Panel>
                <Panel title="Trend · large vs small, equal-weighted"><Trend data={data} /></Panel>
              </div>
            </div>
          ),
        }}
      />
      {open && <AdoptionDrawer sector={open} onClose={() => setOpen(null)} />}
    </>
  );
}
