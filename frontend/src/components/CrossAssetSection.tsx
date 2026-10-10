import { useState } from "react";
import { cn } from "@/lib/cn";
import { useCrossAsset } from "@/hooks/useCrossAsset";
import type { CrossAssetBlock, CrossAssetGroup, CrossAssetSnapshot } from "@/api/types";
import {
  CardHead, ExpandableCard, GraphTile, HowItWorks, NoChart, Panel, StatCell, StatGrid, StatusBadge, TILE_CHART_HEIGHT, ago,
} from "@/components/modelCard";

// Cross-Asset Drivers: what moved equities, Treasuries and gold (cross_asset/ in the backend).
// Overlapping drivers show as one group bar; the split inside a group is marked uncertain.

type AssetKey = "spx" | "ief" | "gld";
type Win = "1w" | "1m" | "3m";
const ASSETS: AssetKey[] = ["spx", "ief", "gld"];
const WIN_WEEKS: Record<Win, number> = { "1w": 1, "1m": 4, "3m": 13 };
const WEAK_R2 = 0.5;
// rounds first, so a tiny negative never prints as "−0.00"
const sgn = (v: number, d = 2) => {
  const r = Number(v.toFixed(d));
  return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toFixed(d)}`;
};

// Same rule as the backend's summary_line, but for the window being viewed.
const summary = (b: CrossAssetBlock, win: Win) =>
  "Biggest drivers: " +
  [...b.windows[win].groups]
    .sort((x, y) => Math.abs(y.contribution) - Math.abs(x.contribution))
    .slice(0, 2)
    .map((g) => `${g.label} ${sgn(g.contribution)} pts`)
    .join(", ") +
  ".";

function cellBg(v: number, unexplained = false) {
  const k = Math.min(1, Math.abs(v));
  if (unexplained) return `rgba(113,113,122,${0.12 + k * 0.3})`;
  return v >= 0 ? `rgba(22,163,74,${0.08 + k * 0.55})` : `rgba(220,38,38,${0.08 + k * 0.55})`;
}

// union of group rows across assets, in first-seen order
function groupRows(s: CrossAssetSnapshot): { group: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const a of ASSETS) for (const g of s.assets[a].windows["1w"].groups) if (!seen.has(g.group)) seen.set(g.group, g.label);
  return [...seen].map(([group, label]) => ({ group, label }));
}

function Heatmap({ s }: { s: CrossAssetSnapshot }) {
  const rows = groupRows(s);
  return (
    <div style={{ minHeight: TILE_CHART_HEIGHT }}>
      <table className="w-full text-xs num">
        <thead>
          <tr className="text-muted">
            <th className="text-left font-medium pb-1" />
            {ASSETS.map((a) => <th key={a} className="font-medium">{s.assets[a].name}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ group, label }) => (
            <tr key={group}>
              <td className="text-left text-text-2 py-[2px] pr-2 whitespace-nowrap">{label}</td>
              {ASSETS.map((a) => {
                const g = s.assets[a].windows["1w"].groups.find((x) => x.group === group);
                return g ? (
                  <td key={a} className="text-center font-mono rounded" style={{ background: cellBg(g.contribution) }}>{sgn(g.contribution)}</td>
                ) : <td key={a} className="text-center text-muted-2">·</td>;
              })}
            </tr>
          ))}
          <tr>
            <td className="text-left text-text-2 py-[2px]">Unexplained</td>
            {ASSETS.map((a) => {
              const u = s.assets[a].windows["1w"].unexplained;
              return <td key={a} className="text-center font-mono rounded" style={{ background: cellBg(u, true) }}>{sgn(u)}</td>;
            })}
          </tr>
          <tr className="border-t border-border">
            <td className="text-left font-semibold pt-1">Actual</td>
            {ASSETS.map((a) => {
              const m = s.assets[a].windows["1w"].move;
              return <td key={a} className={cn("text-center font-mono font-bold pt-1", m >= 0 ? "text-success" : "text-danger")}>{sgn(m)}%</td>;
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

type Row = CrossAssetGroup | { group: "unexplained"; label: string; contribution: number; members: [] };

function Waterfall({ block, win }: { block: CrossAssetBlock; win: Win }) {
  const [open, setOpen] = useState<string | null>(null);
  const w = block.windows[win];
  const items: Row[] = [
    ...[...w.groups].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)),
    { group: "unexplained", label: "Unexplained", contribution: w.unexplained, members: [] },
  ];
  let run = 0;
  const pts = [0, ...items.map((i) => (run += i.contribution)), w.move];
  const lo = Math.min(0, ...pts), hi = Math.max(0, ...pts), span = hi - lo || 1;
  const pct = (v: number) => ((v - lo) / span) * 100;
  const bar = (a: number, b: number, color: string) => (
    <div className="absolute top-0 h-5 rounded-sm"
      style={{ left: `${pct(Math.min(a, b))}%`, width: `${Math.max(0.6, (Math.abs(b - a) / span) * 100)}%`, background: color }} />
  );
  const zero = <div className="absolute -top-1 -bottom-1 border-l border-dashed border-border-strong" style={{ left: `${pct(0)}%` }} />;
  run = 0;
  return (
    <div className="space-y-1.5">
      {items.map((it) => {
        const a = run;
        run += it.contribution;
        const color = it.group === "unexplained" ? "#a1a1aa" : it.contribution >= 0 ? "#16a34a" : "#dc2626";
        const multi = it.members.length > 1;
        const single = it.members.length === 1 ? it.members[0] : null;
        return (
          <div key={it.group}>
            <div className="flex items-center text-xs" data-stop={multi || undefined}
              onClick={() => multi && setOpen(open === it.group ? null : it.group)}>
              <span className={cn("w-32 text-text-2", multi && "cursor-pointer hover:text-accent")}>
                {multi ? (open === it.group ? "▾ " : "▸ ") : ""}{it.label}
              </span>
              <span className="w-24 text-muted font-mono">
                {single ? `${sgn(single.move, 1)} ${single.unit}` : it.group === "unexplained" ? "drift + noise" : ""}
              </span>
              <div className="relative flex-1 h-5 mx-3">{zero}{bar(a, run, color)}</div>
              <span className="w-14 text-right font-mono">{sgn(it.contribution)}</span>
            </div>
            {multi && open === it.group && "max_pairwise_corr" in it && (
              <div className="ml-4 mt-1 mb-2 rounded-md bg-surface-2 px-2.5 py-1.5 text-xs">
                <div className="text-warning mb-1">
                  Split is uncertain: these move together (max correlation {it.max_pairwise_corr?.toFixed(2) ?? "—"}). The group total is reliable.
                </div>
                {it.members.map((m) => (
                  <div key={m.factor} className="flex justify-between font-mono">
                    <span className="font-sans text-text-2">{m.label} ({sgn(m.move, 1)} {m.unit})</span><span>{sgn(m.contribution)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
      <div className="flex items-center text-xs border-t border-border pt-1.5 font-semibold">
        <span className="w-32">Actual move</span><span className="w-24" />
        <div className="relative flex-1 h-5 mx-3">{zero}{bar(0, w.move, "#0a0a0a")}</div>
        <span className={cn("w-14 text-right font-mono", w.move >= 0 ? "text-success" : "text-danger")}>{sgn(w.move)}%</span>
      </div>
    </div>
  );
}

function Surprises({ s, win }: { s: CrossAssetSnapshot; win: Win }) {
  const since = (weeks: number) => new Date(new Date(s.week_end).getTime() - weeks * 7 * 864e5);
  let rows = s.surprises.filter((r) => new Date(r.release_date) > since(WIN_WEEKS[win]));
  const fellBack = rows.length === 0 && win === "1w";
  if (fellBack) rows = s.surprises.filter((r) => new Date(r.release_date) > since(4));
  return (
    <Panel title={`Data surprises in window${fellBack ? " (1M shown: none this week)" : ""}`}>
      {rows.length === 0 ? (
        <div className="text-xs text-muted">No verified releases in this window.</div>
      ) : (
        <table className="w-full text-xs num">
          <thead>
            <tr className="text-muted text-left">
              <th className="font-medium py-1">Release</th><th className="font-medium">Date</th>
              <th className="font-medium text-right">Actual</th><th className="font-medium text-right">Consensus</th>
              <th className="font-medium text-right">Surprise (z)</th><th className="font-medium text-right">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((r) => (
              <tr key={r.series + r.release_date}>
                <td className="py-1.5">{r.label}</td><td>{r.release_date}</td>
                <td className="text-right font-mono">{r.actual}{r.unit}</td>
                <td className="text-right font-mono">{r.consensus}{r.unit}</td>
                <td className={cn("text-right font-mono", r.z > 0 ? "text-success" : r.z < 0 ? "text-danger" : "")}>{sgn(r.z, 1)}</td>
                <td className="text-right">
                  <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">cited ↗</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

const HOW_SHORT =
  "Each week, every driver's move is measured, and data releases count only as their surprise vs consensus. A ridge regression learns how much each driver moves the asset; contribution = sensitivity × move.";
const HOW_STEPS = [
  <>Each Friday, measure every driver's weekly move. Data releases count only as their <b>surprise</b> vs the consensus forecast.</>,
  <>A ridge regression over the last 104 weeks learns how much each driver moves each asset.</>,
  <>Contribution = sensitivity × this period's move. What's left is Unexplained, so the bars add up to the actual move.</>,
];

export function CrossAssetSection({ expanded, onToggle }: { expanded: boolean; onToggle: () => void }) {
  const { data: s } = useCrossAsset();
  const [asset, setAsset] = useState<AssetKey>("spx");
  const [win, setWin] = useState<Win>("1w");
  const name = "Cross-Asset Drivers";
  if (!s) {
    return (
      <ExpandableCard expanded={false} onToggle={() => {}}
        collapsed={
          <GraphTile name={name} value={<span className="text-muted">—</span>} caption="Not run yet">
            <NoChart text="Click Refresh to build the first snapshot." />
          </GraphTile>
        }
        full={{ left: null, right: null }} />
    );
  }
  const b = s.assets[asset];
  const fresh = Date.now() - new Date(s.generated_at).getTime() < 8 * 864e5;
  return (
    <ExpandableCard
      expanded={expanded}
      onToggle={onToggle}
      collapsed={
        <GraphTile name={name} value={<span className="text-text">1W</span>} caption={`% pts of the week to ${s.week_end} by driver`}>
          <Heatmap s={s} />
        </GraphTile>
      }
      full={{
        left: (
          <>
            <CardHead name={name} kind="Weekly driver attribution"
              badge={<StatusBadge status={fresh ? "fresh" : "stale"} text={`Updated ${ago(s.generated_at)}`} />}
              expanded onCollapse={onToggle} />
            <div className="mt-4 flex items-baseline gap-2.5">
              <span className={cn("font-mono text-2xl font-bold", b.windows[win].move >= 0 ? "text-success" : "text-danger")}>
                {sgn(b.windows[win].move)}%
              </span>
              <span className="text-sm text-muted">{b.name}, {win.toUpperCase()} to {s.week_end}</span>
            </div>
            <p className="text-[13px] text-text-2 mt-2 leading-snug">{summary(b, win)}</p>
            <HowItWorks short={HOW_SHORT} steps={HOW_STEPS} expanded docsId="cross-asset" />
            <div className="mt-4">
              <StatGrid>
                {ASSETS.map((a) => {
                  const r2 = s.assets[a].oos_r2;
                  return (
                    <StatCell key={a} label={`${s.assets[a].name}: explained out-of-sample`}
                      value={r2 == null ? "—" : `${Math.round(r2 * 100)}%`} warn={r2 != null && r2 < WEAK_R2} />
                  );
                })}
                <StatCell label="Releases checked" value={`${s.releases_checked.ok} / ${s.releases_checked.total}`} />
              </StatGrid>
            </div>
            {s.data_gaps.length > 0 && (
              <div className="mt-3.5 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2 text-xs text-text-2">
                <b className="text-warning">Data gaps:</b>
                <ul className="list-disc pl-4 mt-1 space-y-0.5">
                  {s.data_gaps.slice(0, 6).map((g) => <li key={g}>{g}</li>)}
                </ul>
              </div>
            )}
          </>
        ),
        right: (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="inline-flex flex-wrap rounded-lg border border-border p-0.5 text-sm font-medium">
                {ASSETS.map((a) => (
                  <button key={a} onClick={() => setAsset(a)}
                    className={cn("px-3 py-1 rounded-md", a === asset ? "bg-accent-soft text-accent" : "text-text-2")}>
                    {s.assets[a].name} <span className="font-mono text-xs">{sgn(s.assets[a].windows[win].move)}%</span>
                  </button>
                ))}
              </div>
              <div className="inline-flex rounded-lg border border-border p-0.5 text-xs font-semibold">
                {(["1w", "1m", "3m"] as Win[]).map((w) => (
                  <button key={w} onClick={() => setWin(w)}
                    className={cn("px-2.5 py-1 rounded-md", w === win ? "bg-accent text-white" : "text-muted")}>
                    {w.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            <Panel title={`What moved ${b.name} (percentage points)`}><Waterfall block={b} win={win} /></Panel>
            <Surprises s={s} win={win} />
          </>
        ),
      }}
    />
  );
}
