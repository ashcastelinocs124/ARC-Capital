import { useState, type ReactNode } from "react";
import { useModels } from "@/hooks/useModels";
import { useAdoptionSummary } from "@/hooks/useAdoption";
import { useCrossAsset } from "@/hooks/useCrossAsset";
import type { ModelCard } from "@/api/endpoints";
import { cn } from "@/lib/cn";
import { AdoptionSection } from "@/components/AdoptionSection";
import { CrossAssetSection } from "@/components/CrossAssetSection";
import { Area, AreaChart, CartesianGrid, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CardBoundary, CardHead, ExpandableCard, GraphTile, HowItWorks, NoChart, Panel, TILE_CHART_HEIGHT } from "@/components/modelCard";
import { PRIVATE_MODELS, type ModelId } from "@/models/registry";
import { C } from "@/lib/theme";

const WEAK_ACCURACY = 0.55; // near coin-flip for a binary up/down call
const MAX_DATA_LAG_MONTHS = 3;

// "How it works" copy per forecaster id (see castelino/forecast/regime.py and risk_off.py).
const HOW: Record<string, { short: string; steps: ReactNode[] }> = {
  growth: {
    short:
      "An XGBoost classifier reads the last 3 months of five leading indicators and outputs the probability that manufacturing is in expansion next month.",
    steps: [
      <><b>Target:</b> mean of the Empire State and Philly Fed manufacturing diffusion indexes (an ISM proxy; 0 = neutral). Label = 1 if next month's value is above 0 (expansion).</>,
      <><b>Inputs:</b> 10-year Treasury yield, initial jobless claims, the Philly Fed leading index, cyclicals vs defensives (XLY/XLP) and real disposable income, each with 3 monthly lags.</>,
      <><b>Model:</b> 100 depth-1 boosted trees on monthly data since 2000; the output is P(up), and the call is "up" at 50% or more.</>,
      <><b>Scoring:</b> walk-forward over 5 folds (train on the past, test on the next block) for accuracy and Brier score.</>,
      <><b>Refresh:</b> the Update Agent refits daily and only promotes a refit whose Brier score is not worse than the current model by more than 0.02.</>,
    ],
  },
  inflation: {
    short:
      "The same XGBoost setup predicts whether CPI inflation accelerates next month, from price, wage, energy, commodity, currency and inflation-expectations series.",
    steps: [
      <><b>Target:</b> CPI All Items (seasonally adjusted). Label = 1 if next month's CPI m/m change is larger than this month's (accelerating).</>,
      <><b>Inputs:</b> PPI, WTI and Brent crude, the Bloomberg Commodity Index, 5-year and 10-year breakevens, the trade-weighted dollar, UMich 1-year expectations, rent CPI, hourly earnings and Case-Shiller home prices, as 1-month and 12-month % changes with 3 monthly lags.</>,
      <><b>Model:</b> 100 depth-1 boosted trees on monthly data since 2000; the output is P(up).</>,
      <><b>Scoring:</b> 5-fold walk-forward accuracy and Brier score.</>,
      <><b>Refresh:</b> daily refit behind the same Brier-score promotion gate.</>,
    ],
  },
  risk_off: {
    short:
      "Predicts whether the S&P 500 falls more than 5% peak-to-trough in the 30 days after month-end, from credit spreads, volatility and the dollar.",
    steps: [
      <><b>Label:</b> 1 if SPY's peak-to-trough drop in the next 30 days exceeds 5%.</>,
      <><b>Inputs:</b> high-yield and investment-grade spreads, VIX, MOVE bond volatility, the broad dollar and the HYG/IEF credit ratio, each with 1–3 monthly lags.</>,
      <><b>Model:</b> 200 depth-4 boosted trees with row and feature sampling; class weights rebalance the rare drawdowns.</>,
      <><b>Output:</b> probability of a risk-off drawdown; shows "Not trained" until a model is saved.</>,
    ],
  },
};

// model id -> section anchor on /docs
const DOCS_ID: Record<string, string> = { growth: "pulse", inflation: "pressure", risk_off: "risk-off" };

function ago(iso: string) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 60) return `${mins}m ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}

function monthLabel(ym: string) {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1).toLocaleString("en-US", { month: "short", year: "numeric" });
}

function monthsBehind(ym: string) {
  const [y, m] = ym.split("-").map(Number);
  const now = new Date();
  return (now.getFullYear() - y) * 12 + (now.getMonth() + 1 - m);
}

function Badge({ card }: { card: ModelCard }) {
  const cls = {
    fresh: "bg-success-soft text-success",
    stale: "bg-warning-soft text-warning",
    missing: "bg-info-soft text-muted",
  }[card.status];
  const text =
    card.status === "missing"
      ? "Not trained"
      : `${card.status === "fresh" ? "Fresh" : "Stale"} · ${ago(card.trained_at!)}`;
  return <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full whitespace-nowrap", cls)}>{text}</span>;
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="text-xs text-muted">
      {label}
      <div className={cn("font-mono font-semibold text-sm num", warn ? "text-warning" : "text-text")}>{value}</div>
    </div>
  );
}

function ParamsTable({ card }: { card: ModelCard }) {
  return (
    <table className="w-full text-xs">
      <tbody>
        {(card.parameters ?? []).map((p) => (
          <tr key={p.name} className="border-t border-border first:border-0">
            <td className="py-1.5 font-mono">{p.name}</td>
            <td className="py-1.5 font-mono font-semibold text-right pr-3">{String(p.value)}</td>
            <td className="py-1.5 text-muted">{p.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SourcesTable({ card }: { card: ModelCard }) {
  return (
    <table className="w-full text-xs">
      <tbody>
        {(card.sources ?? []).map((s) => (
          <tr key={s.id} className={cn("border-t border-border first:border-0", !s.used && "opacity-50")}>
            {/* ponytail: provider + ref stacked under the name so long refs (CSV paths) can't overflow the panel */}
            <td className="py-1.5">
              {s.name}
              {s.role === "target" && <span className="ml-1.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-accent-soft text-accent">target</span>}
              {!s.used && <span className="ml-1.5 text-[10px] text-muted">(skipped in last fit)</span>}
              <div className="text-muted mt-0.5">
                {s.provider} · <span className="font-mono break-all">{s.ref}</span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Predicts({ card }: { card: ModelCard }) {
  if (!card.predicts) return null;
  return (
    <div className="mt-3.5 rounded-lg bg-surface-2 border border-border px-3 py-2.5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Predicts</div>
      <div className="text-sm text-text mt-0.5">{card.predicts.question}</div>
      <div className="text-xs text-muted mt-0.5">Output: {card.predicts.output}</div>
    </div>
  );
}


function Summary({ card, expanded, onToggle }: { card: ModelCard; expanded: boolean; onToggle: () => void }) {
  const how = HOW[card.id];
  const head = <CardHead name={card.name} kind={card.kind} badge={<Badge card={card} />} expanded={expanded} onCollapse={onToggle} />;
  const howBlock = how && <HowItWorks short={how.short} steps={how.steps} expanded={expanded} docsId={DOCS_ID[card.id]} />;

  if (card.status === "missing") {
    return (
      <>
        {head}
        <div className="text-center text-sm text-muted py-6">No forecast on disk yet.</div>
        {howBlock}
        <Predicts card={card} />
      </>
    );
  }

  const pct = Math.round((card.prob ?? 0) * 100);
  const weak = card.accuracy != null && card.accuracy < WEAK_ACCURACY;
  const lagging = !!card.feature_month && monthsBehind(card.feature_month) > MAX_DATA_LAG_MONTHS;
  const notes = [
    weak && "Accuracy is close to a coin flip",
    lagging && `input data lags ${monthsBehind(card.feature_month!)} months behind today`,
  ].filter(Boolean) as string[];

  return (
    <>
      {head}

      <div className="mt-4 flex items-baseline gap-2.5">
        <span className={cn("font-mono text-2xl font-bold", card.up ? "text-success" : "text-danger")}>
          {card.up ? "▲" : "▼"} {pct}%
        </span>
        <span className="text-sm text-muted">
          {card.prob_label} for {card.target_month && monthLabel(card.target_month)}
        </span>
      </div>
      <div className="h-1.5 bg-surface-3 rounded mt-1.5 mb-4 overflow-hidden">
        <div className={cn("h-full", card.up ? "bg-success" : "bg-danger")} style={{ width: `${pct}%` }} />
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 border-t border-border pt-3.5">
        {card.accuracy != null && (
          <Stat label="Walk-forward accuracy" value={`${(card.accuracy * 100).toFixed(1)}%`} warn={weak} />
        )}
        {card.brier != null && <Stat label="Brier score" value={card.brier.toFixed(3)} />}
        {card.n_test != null && <Stat label="Test months" value={String(card.n_test)} />}
        {card.model_version && <Stat label="Model version" value={card.model_version} />}
        {card.feature_month && (
          <Stat label="Data through" value={monthLabel(card.feature_month)} warn={lagging} />
        )}
      </div>

      {notes.length > 0 && (
        <div className="mt-3 text-xs bg-warning-soft text-warning rounded-lg px-3 py-2">
          {notes.join(", and ").replace(/^./, (c) => c.toUpperCase())}.
        </div>
      )}
      {card.accuracy == null && (
        <div className="mt-3 text-xs text-muted">This model doesn't save accuracy metrics.</div>
      )}
      {howBlock}
      <Predicts card={card} />
    </>
  );
}

// What each forecaster's tile chart plots (the series its label is built from).
const SERIES: Record<string, { name: string; unit: string }> = {
  growth: { name: "Empire State + Philly Fed composite, 0 = neutral", unit: "" },
  inflation: { name: "CPI month-over-month", unit: "%" },
};
const TILE_MONTHS = 36;

function HistoryChart({ card }: { card: ModelCard }) {
  const rows = (card.history ?? []).slice(-TILE_MONTHS);
  if (rows.length < 2) return <NoChart text="History appears after the next Refresh." />;
  const unit = SERIES[card.id]?.unit ?? "";
  const last = rows[rows.length - 1];
  return (
    <ResponsiveContainer width="100%" height={TILE_CHART_HEIGHT}>
      <AreaChart data={rows} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={C.border} />
        <XAxis dataKey="month" tick={{ fontSize: 10, fill: C.muted2 }} axisLine={false} tickLine={false} tickFormatter={(m: string) => m.slice(0, 4)}
          ticks={rows.filter((r) => r.month.endsWith("-01")).map((r) => r.month)} />
        <YAxis orientation="right" tick={{ fontSize: 10, fill: C.muted2 }} axisLine={false} tickLine={false} width={40} tickCount={4}
          tickFormatter={(v: number) => `${+v.toFixed(1)}${unit}`} />
        <ReferenceLine y={0} stroke={C.muted2} strokeDasharray="3 4" />
        <Tooltip formatter={(v: number) => `${v.toFixed(2)}${unit}`} labelFormatter={(m: string) => monthLabel(m)} />
        <Area dataKey="value" name={SERIES[card.id]?.name} stroke={C.text} strokeWidth={1.6} fill={C.text} fillOpacity={0.04} dot={false} isAnimationActive={false} />
        <ReferenceDot x={last.month} y={last.value} r={5} fill={card.up ? C.success : C.danger} stroke={C.surface} strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// The question each forecaster answers, in plain words, for its target month.
const QUESTION: Record<string, { kicker: string; ask: (month: string) => string }> = {
  growth: { kicker: "Growth nowcast", ask: (m) => `Will factory surveys show expansion in ${m}?` },
  inflation: { kicker: "Inflation nowcast", ask: (m) => `Will CPI inflation speed up in ${m}?` },
  risk_off: { kicker: "Risk nowcast", ask: () => "Is a risk-off episode coming?" },
};
const longMonth = (ym: string) => new Date(`${ym}-01T00:00:00`).toLocaleDateString("en-US", { month: "long" });

function Tile({ card }: { card: ModelCard }) {
  const q = QUESTION[card.id] ?? { kicker: "Model", ask: () => card.name };
  const month = card.target_month ? longMonth(card.target_month) : "the coming month";
  if (card.status === "missing") {
    return (
      <GraphTile kicker={q.kicker} name={card.name} question={q.ask(month)} value="—" caption="Not trained yet">
        <NoChart text="No forecast on disk yet." />
      </GraphTile>
    );
  }
  return (
    <GraphTile
      kicker={q.kicker}
      name={card.name}
      question={q.ask(month)}
      value={`${Math.round((card.prob ?? 0) * 100)}%`}
      verdict={card.up ? { text: "Likely yes", tone: "up" } : { text: "Likely no", tone: "dn" }}
      sub={`${card.prob_label}${card.target_month ? ` · ${monthLabel(card.target_month)}` : ""}`}
      stale={card.status === "stale" && card.feature_month ? `Data through ${monthLabel(card.feature_month).split(" ")[0]} · stale` : undefined}
      caption={`${SERIES[card.id]?.name ?? card.kind}, last 3 years · dot = next month's call`}
    >
      <HistoryChart card={card} />
    </GraphTile>
  );
}

function Card({ card, expanded, onToggle }: { card: ModelCard; expanded: boolean; onToggle: () => void }) {
  return (
    <ExpandableCard
      expanded={expanded}
      onToggle={onToggle}
      collapsed={<Tile card={card} />}
      full={{
        left: <Summary card={card} expanded onToggle={onToggle} />,
        right: (
          <div className="grid md:grid-cols-2 gap-3.5">
            <Panel title={`Parameters (${card.parameters?.length ?? 0})`}><ParamsTable card={card} /></Panel>
            <Panel title={`Sources (${card.sources?.length ?? 0})`}><SourcesTable card={card} /></Panel>
          </div>
        ),
      }}
    />
  );
}

interface CardProps {
  expanded: boolean;
  onToggle: () => void;
}

// One /models forecaster card, by its backend id; renders nothing until /models has loaded.
function ForecastCard({ id, ...p }: CardProps & { id: string }) {
  const card = useModels().data?.find((c) => c.id === id);
  return card ? <Card card={card} {...p} /> : null;
}

// One component per private model (registry.ts); Fear & Greed · Sector Sentiment is public, on Radar.
const COMPONENTS: Record<Exclude<ModelId, "sector-sentiment">, (p: CardProps) => ReactNode> = {
  pulse: (p) => <ForecastCard id="growth" {...p} />,
  pressure: (p) => <ForecastCard id="inflation" {...p} />,
  "risk-off": (p) => <ForecastCard id="risk_off" {...p} />,
  adoption: (p) => <AdoptionSection {...p} />,
  "cross-asset": (p) => <CrossAssetSection {...p} />,
};

// A model whose data breaks its card shows a notice instead of blanking the whole page.
// Live value per model for the header chips (each hook is already used by its card, so no extra fetches).
function useChipValues(): Record<string, string | undefined> {
  const models = useModels().data;
  const adoption = useAdoptionSummary().data;
  const cross = useCrossAsset().data;
  const prob = (id: string) => {
    const p = models?.find((m) => m.id === id)?.prob;
    return p == null ? undefined : `${Math.round(p * 100)}%`;
  };
  const large = adoption && !Array.isArray(adoption) ? adoption.headline?.large_ew : null;
  const move = cross?.assets.spx.windows["1w"].move;
  return {
    pulse: prob("growth"),
    pressure: prob("inflation"),
    "risk-off": prob("risk_off"),
    adoption: large != null ? large.toFixed(1) : undefined,
    "cross-asset": move != null ? `${move >= 0 ? "+" : ""}${move.toFixed(1)}%` : undefined,
  };
}

function Header({ onJump }: { onJump: (id: string) => void }) {
  const values = useChipValues();
  return (
    <section aria-label="Jump to a model">
      <div className="flex flex-wrap gap-2">
        {PRIVATE_MODELS.map((m) => (
          <button key={m.id} onClick={() => onJump(m.id)}
            className="flex items-baseline gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 text-[13px] hover:border-border-strong">
            <b className="font-semibold text-text">{m.name}</b>
            {values[m.id] && <span className="num text-muted">{values[m.id]}</span>}
          </button>
        ))}
      </div>
      <div className="mt-2.5 text-xs text-muted">Read-only. Refit daily by the Update Agent; a model older than 24 hours is marked stale. Click a card for its method, inputs and track record.</div>
    </section>
  );
}

const WIDE = new Set<string>(["adoption", "cross-asset"]); // full-width tiles (4 models: 2 halves + 2 wide)

export default function ModelsPage() {
  const { isLoading } = useModels();
  const [expanded, setExpanded] = useState<string | null>(null); // one card open at a time
  const toggle = (id: string) => setExpanded((cur) => (cur === id ? null : id));
  const jump = (id: string) => document.getElementById(`model-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="space-y-6 p-5 md:p-8">
      <Header onJump={jump} />
      <div className="grid gap-5 md:grid-cols-2">
        {isLoading && <div className="text-sm text-muted">Loading…</div>}
        {PRIVATE_MODELS.map((m) => {
          const Model = COMPONENTS[m.id];
          return (
            <div key={m.id} id={`model-${m.id}`} className={cn("min-w-0 scroll-mt-4", (expanded === m.id || WIDE.has(m.id)) && "md:col-span-2")}>
              <CardBoundary name={m.name}>
                <Model expanded={expanded === m.id} onToggle={() => toggle(m.id)} />
              </CardBoundary>
            </div>
          );
        })}
      </div>
    </div>
  );
}
