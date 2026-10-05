import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAdoptionCompanies, useAdoptionSummary } from "@/hooks/useAdoption";
import type { AdoptionCell, AdoptionCompany, Bucket } from "@/api/adoption";
import { cn } from "@/lib/cn";

const SECTORS = [
  "Information Technology", "Communication Services", "Consumer Discretionary", "Financials",
  "Health Care", "Industrials", "Consumer Staples", "Energy", "Utilities", "Materials", "Real Estate",
];

const f = (x: number | null | undefined, d = 1) => (x == null ? "—" : x.toFixed(d));
const signed = (x: number | null | undefined) => (x == null ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(1)}`);

function heat(v: number): React.CSSProperties {
  const t = Math.max(0, Math.min(1, (v - 25) / 55));
  return { background: `rgba(0,135,68,${(0.1 + t * 0.55).toFixed(2)})`, color: t > 0.62 ? "#fff" : undefined };
}

function Score({ cell }: { cell?: AdoptionCell }) {
  if (!cell || cell.ew == null) return <span className="text-muted">—</span>;
  return (
    <>
      <span
        className={cn(
          "inline-block min-w-[44px] text-center rounded px-1.5 font-semibold num",
          cell.thin && "outline-dashed outline-1 outline-warning bg-warning-soft text-warning",
        )}
        style={cell.thin ? undefined : heat(cell.ew)}
      >
        {cell.ew.toFixed(0)}
      </span>
      <span className="ml-1 text-[11px] text-muted">n={cell.n}</span>
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs text-muted">{label}</div>
        <div className="text-2xl font-semibold num">{value}</div>
        {sub && <div className="text-xs text-muted">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function CompanyTable({ label, rows }: { label: string; rows: AdoptionCompany[] }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-muted mb-1">{label}</div>
      {rows.length === 0 ? (
        <div className="text-xs text-muted">No companies in this cell.</div>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-muted bg-surface-2">
            <tr>
              <th className="text-left px-2 py-1">Ticker</th>
              <th className="text-right px-2">Score</th>
              <th className="text-right px-2">Talk</th>
              <th className="text-right px-2">Hire</th>
              <th className="text-right px-2">Spend</th>
              <th className="text-left px-2">Top claim</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker} className="border-t border-border align-top">
                <td className="px-2 py-1 font-mono">{r.ticker}</td>
                <td className="text-right px-2 num font-semibold">{f(r.score, 0)}</td>
                <td className="text-right px-2 num">{f(r.s_talk, 0)}</td>
                <td className="text-right px-2 num">{f(r.s_hire, 0)}</td>
                <td className="text-right px-2 num">{f(r.s_spend, 0)}</td>
                <td className="px-2 py-1 text-muted">{r.claims[0] ? `"${r.claims[0].quote.slice(0, 110)}"` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Drill({ sector }: { sector: string }) {
  const large = useAdoptionCompanies(sector, "large");
  const small = useAdoptionCompanies(sector, "small");
  const pick = (d: AdoptionCompany[] | undefined) => (Array.isArray(d) ? d : []);
  return (
    <div className="mt-4 border-t border-border pt-4">
      <div className="text-sm font-semibold mb-2">{sector}</div>
      <div className="grid md:grid-cols-2 gap-4">
        <CompanyTable label="Large cap" rows={pick(large.data)} />
        <CompanyTable label="Small cap" rows={pick(small.data)} />
      </div>
    </div>
  );
}

export function AdoptionSection() {
  const { data, isLoading } = useAdoptionSummary();
  const [selected, setSelected] = useState<string | null>(null);

  const header = (
    <div>
      <h2 className="text-base font-semibold text-text">AI Adoption Index</h2>
      <p className="text-xs text-muted mt-0.5">
        Top 100 by market cap in the S&amp;P 500 and Russell 2000. Talk and Spend update on new filings; Hire is a
        bi-weekly job-board snapshot. Research metric, not wired into the trading pipeline.
      </p>
    </div>
  );

  if (isLoading) return <div className="pt-6 border-t border-border">{header}<div className="text-sm text-muted mt-3">Loading…</div></div>;
  if (!data || Array.isArray(data) || data.period == null) {
    return (
      <div className="pt-6 border-t border-border">
        {header}
        <div className="text-sm text-muted mt-3">No adoption data yet. Run <code className="font-mono">ckm adoption run</code>.</div>
      </div>
    );
  }

  const h = data.headline;
  const cell = (sector: string, bucket: Bucket) => data.cells.find((c) => c.sector === sector && c.bucket === bucket);
  const rows = data.series.map((p) => ({ period: p.period, Large: p.large_ew, Small: p.small_ew }));

  return (
    <div className="pt-6 border-t border-border space-y-4">
      <div className="flex items-start justify-between gap-4">
        {header}
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full whitespace-nowrap bg-success-soft text-success">
          updated {data.period}
        </span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi label="Large cap, equal-weighted" value={f(h.large_ew)} />
        <Kpi label="Small cap, equal-weighted" value={f(h.small_ew)} />
        <Kpi label="Size spread (small − large)" value={signed(h.spread)} />
        <Kpi label="Large-cap concentration (CW − EW)" value={signed(h.large_concentration)} sub={`small cap: ${signed(h.small_concentration)}`} />
      </div>

      <div className="grid lg:grid-cols-5 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Large vs small, equal-weighted</CardTitle></CardHeader>
          <CardContent className="p-4">
            {rows.length < 2 ? (
              <div className="text-xs text-muted">A trend needs at least two periods.</div>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={rows}>
                  <CartesianGrid stroke="#ececef" />
                  <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="Large" stroke="#008744" strokeWidth={2} dot={false} connectNulls />
                  <Line type="monotone" dataKey="Small" stroke="#71717a" strokeWidth={2} strokeDasharray="4 3" dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader><CardTitle>By sector (GICS) and size bucket</CardTitle></CardHeader>
          <CardContent className="p-4">
            <table className="w-full text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="text-left px-2 py-1">Sector</th>
                  <th className="text-right px-2">Large EW</th>
                  <th className="text-right px-2">Large CW</th>
                  <th className="text-right px-2">Small EW</th>
                  <th className="text-right px-2">Small CW</th>
                </tr>
              </thead>
              <tbody>
                {SECTORS.map((s) => (
                  <tr
                    key={s}
                    onClick={() => setSelected(selected === s ? null : s)}
                    className={cn("border-t border-border cursor-pointer hover:bg-surface-2", selected === s && "bg-accent-soft")}
                  >
                    <td className="px-2 py-1.5">{s}</td>
                    <td className="text-right px-2"><Score cell={cell(s, "large")} /></td>
                    <td className="text-right px-2 num">{f(cell(s, "large")?.cw, 0)}</td>
                    <td className="text-right px-2"><Score cell={cell(s, "small")} /></td>
                    <td className="text-right px-2 num">{f(cell(s, "small")?.cw, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="text-[11px] text-muted mt-2">
              Dashed amber = thin cell (n &lt; 5), indicative only. Click a sector for its companies and source quotes.
            </div>
            {selected && <Drill sector={selected} />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
