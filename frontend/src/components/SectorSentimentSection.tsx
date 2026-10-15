import { useEffect, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { company } from "@/lib/company";
import { cn } from "@/lib/cn";
import { Bar, BarChart, Cell, LabelList, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { useSectorSentiment } from "@/hooks/useSectorSentiment";
import type { FearGreed, SectorExplanation, SectorScore, SectorStockRow } from "@/api/types";
import { Headline, HowItWorks, Panel, StatCell, StatGrid, StatusBadge, ago } from "@/components/modelCard";
import { FearGreedGauge, ZoneBar, ZonePill, zoneColor, zoneOf } from "@/components/FearGreedGauge";
import { C } from "@/lib/theme";

// Fear & Greed · Sector Sentiment, a card on Radar (/macro#sector-sentiment) since 2026-10-15. The needle is the
// market reading (signals/fear_greed.py); each sector's 0-100 score is its divergence = technical − fundamental
// (ported from Arc-Investment-Research/arc-dashboard). Greed / positive divergence = price ahead of fundamentals
// (red), fear / negative = fundamentals nobody is buying (green).

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
function SectorDrawer({ s, names, onClose }: { s: SectorScore; names: Record<string, string>; onClose: () => void }) {
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
              <Stat k="largest contributor" v={`${company(names[e.top_symbol], e.top_symbol)} · ${(e.top_share * 100).toFixed(0)}%`} />
              <Stat k="cap-wt vs equal-wt" v={`${fmt(s.divergence)} / ${fmt(e.equal_weight_divergence)}`} />
              <Stat k="drivers" v={e.drivers.join(" · ")} />
            </div>
            <div className="mt-4 text-xs uppercase tracking-wide text-muted">Contribution to sector divergence</div>
            <div className="mt-1.5 space-y-1">
              {e.contributions.map((c) => (
                <div key={c.symbol} className="grid grid-cols-[150px_1fr_64px] items-center gap-2.5 text-xs">
                  <span className="font-semibold truncate" title={company(names[c.symbol], c.symbol)}>{company(names[c.symbol], c.symbol)}</span>
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
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(0)}%`);
// A stock in a sector and the Semiconductors overlay is one stock in two rows.
function stocksScored(rows: SectorStockRow[]) {
  const n = new Set(rows.map((r) => r.symbol)).size;
  return n < rows.length ? `${n} (${rows.length - n} in two rows)` : String(n);
}
// ponytail: snapshots saved before 2026-10-15 have no fg_score; same mapping as fear_greed.sector_score
const score = (s: SectorScore) => s.fg_score ?? Math.max(0, Math.min(100, Math.round(50 + (25 * s.divergence) / 0.3)));

const HOW: { short: string; steps: ReactNode[] } = {
  short:
    "The needle averages five market signals, each ranked against its own last two years. A sector's score shows how far its stock prices have run ahead of the businesses (greed) or fallen behind them (fear).",
  steps: [
    <><b>The needle:</b> S&amp;P 500 vs its 125-day average; the share of our stocks above their 200-day average; VIX vs its 50-day average; the high-yield bond spread; stocks vs Treasuries over 20 days. Each is ranked 0–100 against its own last 2 years (VIX and the spread upside down) and the needle is their average: CNN's recipe without the put/call ratio, which has no free source.</>,
    <><b>Zones:</b> 0–25 extreme fear · 25–45 fear · 45–55 neutral · 55–75 greed · 75–100 extreme greed.</>,
    <><b>Technical score:</b> RSI-14, MACD histogram, price vs 50- and 200-day averages and 3-month return. Each metric is z-scored across all stocks, clipped at ±3σ, scaled to −1…+1 and averaged.</>,
    <><b>Fundamental score:</b> ⅔ forward: forward P/E vs the sector median (cheaper scores higher) and the 90-day change in analysts' next-year EPS estimate; ⅓ trailing: last fiscal year's revenue growth, earnings growth and P/E vs the sector median. Scored the same way.</>,
    <><b>Sector score</b> = 50 + 83 × divergence, where divergence = technical − fundamental per stock, cap-weighted across the sector's top 10. ±0.30 (the old euphoric / fearful line) lands on 75 / 25.</>,
    <><b>Semiconductors</b> is an extra row, not a GICS sector: the 10 largest chip and chip-equipment stocks. They also count in Technology.</>,
    <><b>Explainer:</b> code works out whether a reading is sector-wide or driven by one stock; an LLM writes the prose, which describes and does not recommend.</>,
  ],
};

const HIST: [keyof FearGreed, string][] = [
  ["previous", "Previous close"], ["week_ago", "1 week ago"], ["month_ago", "1 month ago"], ["year_ago", "1 year ago"],
];

// The dial plus the look-backs; clicking one swings the needle there and leaves a dashed one at today's.
function Needle({ fg }: { fg: FearGreed }) {
  const [shown, setShown] = useState<keyof FearGreed | null>(null);
  const past = shown ? (fg[shown] as number | null) : null;
  return (
    <>
      <div className="mx-auto max-w-[440px]"><FearGreedGauge score={past ?? fg.score} ghost={past != null ? fg.score : null} /></div>
      <div className="mt-1.5 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {HIST.map(([k, label]) => {
          const v = fg[k] as number | null;
          return (
            <button key={k} disabled={v == null} onClick={() => setShown(shown === k ? null : k)}
              className={cn("rounded-lg border bg-surface-2 px-2.5 py-1.5 text-left text-[11px] text-muted disabled:cursor-default",
                shown === k ? "border-accent" : "border-transparent enabled:hover:border-border-strong")}>
              {label}
              <span className="mt-0.5 flex flex-wrap items-baseline gap-x-1.5">
                <b className="num text-[15px] text-text">{v ?? "—"}</b>
                {v != null && <ZonePill score={v} className="px-1.5 py-0 text-[10px]" />}
              </span>
            </button>
          );
        })}
      </div>
    </>
  );
}

// One bar per sector from the 50 line, coloured by its zone; click one for its breakdown.
function SectorBars({ sectors, onOpen }: { sectors: SectorScore[]; onOpen: (s: string) => void }) {
  const rows = sectors.map((s) => ({ sector: s.sector, score: score(s), off: score(s) - 50 })).sort((a, b) => b.score - a.score);
  return (
    <ResponsiveContainer width="100%" height={rows.length * 22 + 8}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 34, left: 0, bottom: 0 }} barCategoryGap={3}>
        <XAxis type="number" domain={[-50, 50]} hide />
        <YAxis type="category" dataKey="sector" width={140} tick={{ fontSize: 11, width: 200, fill: C.muted }} interval={0} tickLine={false} axisLine={false} />
        <ReferenceLine x={0} stroke={C.border} />
        <Bar dataKey="off" radius={3} isAnimationActive={false} cursor="pointer" onClick={(_, i) => onOpen(rows[i].sector)}>
          {rows.map((r) => <Cell key={r.sector} fill={zoneColor(zoneOf(r.score))} />)}
          <LabelList dataKey="score" position="right" style={{ fontSize: 10.5, fill: C.muted, fontVariantNumeric: "tabular-nums" }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function Signals({ fg }: { fg: FearGreed }) {
  return (
    <div>
      {fg.components.map((c) => (
        <div key={c.key} className="grid grid-cols-[minmax(0,1fr)_72px_26px_92px] items-center gap-2.5 border-t border-border py-2 text-xs first:border-t-0 sm:grid-cols-[minmax(0,1fr)_96px_26px_96px]">
          <span><b className="font-semibold text-text">{c.name}</b> <span className="text-muted">· {c.raw}</span></span>
          <ZoneBar score={c.score} />
          <b className="num text-right text-text">{c.score}</b>
          <ZonePill score={c.score} className="text-center" />
        </div>
      ))}
    </div>
  );
}

function SectorRows({ sectors, onOpen }: { sectors: SectorScore[]; onOpen: (s: string) => void }) {
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-muted">
            <tr>
              <th className="text-left py-1 font-medium">Sector</th>
              <th className="text-right font-medium px-1">Tech</th>
              <th className="text-right font-medium px-1">Fund</th>
              <th className="text-right font-medium px-1">Divergence</th>
              <th className="text-right font-medium">Score</th>
            </tr>
          </thead>
          <tbody>
            {sectors.map((s) => (
              <tr key={s.sector} onClick={() => onOpen(s.sector)} className="border-t border-border cursor-pointer hover:bg-surface-2">
                <td className="py-1.5">
                  {s.sector}
                  {s.part_of && (
                    <span className="ml-1.5 whitespace-nowrap rounded-full border border-accent/40 px-1.5 text-[9.5px] font-semibold uppercase tracking-wide text-accent">
                      in {s.part_of === "Technology" ? "Tech" : s.part_of}
                    </span>
                  )}
                </td>
                <td className="text-right font-mono px-1">{fmt(s.tech_score)}</td>
                <td className="text-right font-mono px-1">{fmt(s.fund_score)}</td>
                <td className="text-right px-1"><DivergenceChip v={s.divergence} /></td>
                <td className="whitespace-nowrap text-right">
                  <b className="num mr-1.5">{score(s)}</b>
                  <ZonePill score={score(s)} className="px-1.5 py-px text-[9.5px]" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-[11px] text-muted mt-1.5">Click a sector for its constituents and the explainer.</div>
    </>
  );
}

function Narrative({ snap }: { snap: { narrative: string | null; narrative_generated_at: string | null } }) {
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
        ["Fwd P/E vs sector", (r) => (r.fwd_pe_rel != null ? `${r.fwd_pe_rel.toFixed(1)}×` : "—")],
        ["EPS est. 90d", (r) => pct(r.eps_rev_90d)],
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
            <th className="text-left py-1 font-medium">Company</th>
            {cols.map(([h]) => <th key={h} className="text-right font-medium px-1">{h}</th>)}
            <th className="text-right font-medium">Div</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className="border-t border-border" title={r.name}>
              <td className="py-1.5 pr-2 font-semibold">
                {company(r.name, r.symbol)}
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

export function SectorSentimentSection() {
  const { data: snap, isLoading } = useSectorSentiment();
  const [full, setFull] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);

  if (!snap?.sectors?.length) {
    return <p className="text-sm text-muted">{isLoading ? "Loading…" : "No Sector Sentiment snapshot yet."}</p>;
  }

  const { sectors, fear_greed: fg } = snap;
  const fresh = (Date.now() - new Date(snap.as_of).getTime()) / 3_600_000 <= FRESH_HOURS;
  const byScore = [...sectors].sort((a, b) => score(a) - score(b));
  const [fearful, greedy] = [byScore[0], byScore[byScore.length - 1]];
  const top = sectors.reduce((a, b) => (Math.abs(b.divergence) > Math.abs(a.divergence) ? b : a), sectors[0]);
  const openSector = sectors.find((s) => s.sector === open) ?? null;
  const tableSector = sectors.find((s) => s.sector === picked) ?? sectors[0];
  const rows = snap.stocks.filter((r) => r.sector === tableSector?.sector).sort((a, b) => b.market_cap - a.market_cap);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          {fg ? (
            <>
              <span className="num text-[34px] font-bold leading-none tracking-[-0.02em] text-text">{fg.score}</span>
              <ZonePill score={fg.score} className="px-2.5 py-1 text-xs" />
              {fg.week_ago != null && <span className="text-[12.5px] text-muted">was {fg.week_ago} a week ago</span>}
            </>
          ) : (
            <span className="text-[12.5px] text-muted">The market needle is missing from this snapshot; the sector scores below are current.</span>
          )}
        </div>
        <span className="flex items-center gap-2">
          <StatusBadge status={fresh ? "fresh" : "stale"} text={`${fresh ? "Fresh" : "Stale"} · ${ago(snap.as_of)}`} />
          <button onClick={() => setFull(!full)}
            className="rounded-full border border-accent/40 bg-accent-soft px-3.5 py-1 text-xs font-semibold text-accent hover:bg-accent-soft-2">
            {full ? "Close ↑" : "Open the full card ↓"}
          </button>
        </span>
      </div>

      <div className="mt-3 grid items-start gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="min-w-0">
          {fg ? <Needle fg={fg} /> : (
            <Headline value={fmt(top.divergence)} label={`${top.sector} — most stretched · ${top.label}`}
              tone={top.divergence >= 0 ? "danger" : "success"} fill={(Math.abs(top.divergence) / 0.5) * 100} />
          )}
        </div>
        <div className="min-w-0">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">Sectors · 0 fear → 100 greed</div>
          <SectorBars sectors={sectors} onOpen={setOpen} />
        </div>
      </div>
      <p className="mt-2.5 border-t border-border pt-2.5 text-[11.5px] text-muted">
        {fg ? "5 market signals, each ranked against its last 2 years" : "Sector scores only"} · most fearful sector{" "}
        <b className="text-text-2">{fearful.sector} {score(fearful)}</b>, most greedy <b className="text-text-2">{greedy.sector} {score(greedy)}</b> · describes, does not recommend
      </p>

      {full && (
        <div className="mt-4 grid gap-3.5">
          {fg && <Panel title={`Market signals (${fg.components.length}) · as of ${fg.as_of}`}><Signals fg={fg} /></Panel>}
          <div className="grid items-start gap-3.5 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Panel title={`Sectors (${sectors.length})`}><SectorRows sectors={sectors} onOpen={setOpen} /></Panel>
            <Panel title={`Stocks · top ${rows.length} by market cap`}>
              <SectorPicker sectors={sectors} value={tableSector?.sector} onPick={setPicked} />
              <Stocks rows={rows} full />
            </Panel>
          </div>
          <div className="grid items-start gap-3.5 md:grid-cols-2">
            <div className="space-y-3.5 min-w-0">
              {snap.narrative && <Panel title="Narrative"><Narrative snap={snap} /></Panel>}
              <StatGrid>
                <StatCell label="Stocks scored" value={stocksScored(snap.stocks)} />
                <StatCell label="As of" warn={!fresh}
                  value={new Date(snap.as_of).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} />
                {fg && <StatCell label="Signals in fear (< 45)" value={`${fg.components.filter((c) => c.score < 45).length} of ${fg.components.length}`} />}
                {top.explanation && <StatCell label={`Breadth (${top.sector})`} value={`${top.explanation.n_agree}/${top.explanation.n_total} same sign`} />}
              </StatGrid>
            </div>
            <HowItWorks short={HOW.short} steps={HOW.steps} expanded docsId="sector-sentiment" />
          </div>
        </div>
      )}
      {openSector && <SectorDrawer s={openSector} names={Object.fromEntries(snap.stocks.map((r) => [r.symbol, r.name]))} onClose={() => setOpen(null)} />}
    </>
  );
}
