import { Component, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Play } from "lucide-react";
import { useModels } from "@/hooks/useModels";
import { useVideos } from "@/hooks/useVideos";
import type { ModelCard } from "@/api/endpoints";
import { cn } from "@/lib/cn";
import { SectorSentimentSection } from "@/components/SectorSentimentSection";
import { AdoptionSection } from "@/components/AdoptionSection";
import { CrossAssetSection } from "@/components/CrossAssetSection";
import { Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CardHead, ExpandableCard, GraphTile, HowItWorks, NoChart, Panel, TILE_CHART_HEIGHT } from "@/components/modelCard";
import { ENABLED_MODELS, type ModelId } from "@/models/registry";

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
  const color = card.up ? "#16a34a" : "#dc2626";
  const call = `${card.target_month ? monthLabel(card.target_month).split(" ")[0] : "Next"}: ${Math.round((card.prob ?? 0) * 100)}% ${card.up ? "▲" : "▼"}`;
  return (
    <ResponsiveContainer width="100%" height={TILE_CHART_HEIGHT}>
      <LineChart data={rows} margin={{ top: 8, right: 72, left: 0, bottom: 0 }}>
        <XAxis dataKey="month" tick={{ fontSize: 10 }} tickFormatter={(m: string) => m.slice(0, 4)}
          ticks={rows.filter((r) => r.month.endsWith("-01")).map((r) => r.month)} />
        <YAxis tick={{ fontSize: 10 }} width={40} tickFormatter={(v: number) => `${+v.toFixed(1)}${unit}`} />
        <ReferenceLine y={0} stroke="#d4d4d7" strokeDasharray="3 3" />
        <Tooltip formatter={(v: number) => `${v.toFixed(2)}${unit}`} labelFormatter={(m: string) => monthLabel(m)} />
        <Line dataKey="value" name={SERIES[card.id]?.name} stroke="#52525b" strokeWidth={1.5} dot={false} isAnimationActive={false} />
        <ReferenceDot x={last.month} y={last.value} r={4} fill={color} stroke="none"
          label={{ value: call, position: "right", fill: color, fontSize: 11, fontWeight: 600 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function Tile({ card }: { card: ModelCard }) {
  if (card.status === "missing") {
    return <GraphTile name={card.name} value={<span className="text-muted">—</span>} caption="Not trained yet"><NoChart text="No forecast on disk yet." /></GraphTile>;
  }
  const pct = Math.round((card.prob ?? 0) * 100);
  return (
    <GraphTile
      name={card.name}
      value={<span className={card.up ? "text-success" : "text-danger"}>{card.up ? "▲" : "▼"} {pct}%</span>}
      caption={`${SERIES[card.id]?.name ?? card.kind} · dot = ${card.prob_label}${card.target_month ? ` for ${monthLabel(card.target_month)}` : ""}`}
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

// One component per model; which ones show is decided in models/registry.ts.
const COMPONENTS: Record<ModelId, (p: CardProps) => ReactNode> = {
  pulse: (p) => <ForecastCard id="growth" {...p} />,
  pressure: (p) => <ForecastCard id="inflation" {...p} />,
  "risk-off": (p) => <ForecastCard id="risk_off" {...p} />,
  "sector-sentiment": (p) => <SectorSentimentSection {...p} />,
  adoption: (p) => <AdoptionSection {...p} />,
  "cross-asset": (p) => <CrossAssetSection {...p} />,
};

// A model whose data breaks its card shows a notice instead of blanking the whole page.
class CardBoundary extends Component<{ name: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="card p-5 text-sm text-muted">
        {this.props.name} couldn't be shown: its latest data is incomplete. Click Refresh to rebuild it.
      </div>
    );
  }
}

const HERO_CHIPS = ["Macro", "AI", "Semiconductors", "Markets"];

function Hero() {
  const latest = useVideos().data?.[0];
  return (
    <section className="flex flex-col gap-8 rounded-3xl border border-border bg-surface bg-[radial-gradient(120%_140%_at_100%_0%,#e6f4ec_0%,rgba(230,244,236,0)_55%)] px-6 py-8 md:flex-row md:items-center md:justify-between md:px-12 md:py-11">
      <div className="min-w-0 flex-1">
        <div className="eyebrow">ARC Research · Models</div>
        <h1 className="mt-4 max-w-3xl text-4xl font-bold leading-[1.04] tracking-[-0.04em] text-text md:text-5xl lg:text-6xl">
          Macro and AI, <span className="text-accent">explained for everyone.</span>
        </h1>
        <p className="mt-4 max-w-xl text-base text-muted md:text-[17px]">
          In-depth research and live models on the economy, markets and the AI stack. No finance background required.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-3">
          <Link to="/docs" className="rounded-full bg-accent px-5 py-2 text-[13px] font-semibold text-white hover:bg-accent-hover">
            Read the docs
          </Link>
          <div className="flex flex-wrap gap-2">
            {HERO_CHIPS.map((c) => (
              <span key={c} className="pill px-3.5 py-1.5 text-[12.5px]">{c}</span>
            ))}
          </div>
        </div>
        {latest && (
          <a href={latest.url} target="_blank" rel="noopener noreferrer" className="group mt-5 inline-flex items-center gap-3">
            <span className="grid h-11 w-[72px] place-items-center overflow-hidden rounded-lg bg-gradient-to-br from-[#0b3d24] via-accent to-[#9ad7b6] text-white">
              {latest.thumbnail ? <img src={latest.thumbnail} alt="" className="col-start-1 row-start-1 h-full w-full object-cover" /> : null}
              <Play className="col-start-1 row-start-1 h-4 w-4 fill-current drop-shadow" />
            </span>
            <span>
              <span className="block text-[13px] font-semibold text-text group-hover:text-accent">{latest.title}</span>
              <span className="text-xs text-muted">Watch the latest video · opens Substack ↗</span>
            </span>
          </a>
        )}
      </div>
      <img
        src="/hero.jpg"
        alt="Manhattan skyline at dusk"
        className="aspect-[3/2] w-full rounded-2xl object-cover shadow-[0_10px_30px_-10px_rgba(0,60,40,0.35)] md:w-[46%] md:shrink-0 lg:w-[52%]"
      />
    </section>
  );
}

export default function ModelsPage() {
  const { isLoading } = useModels();
  const [expanded, setExpanded] = useState<string | null>(null); // one card open at a time
  const toggle = (id: string) => setExpanded((cur) => (cur === id ? null : id));

  return (
    <div className="p-4 md:p-8 space-y-5">
      <Hero />
      <p className="text-xs text-muted">
        Click a graph for that model's card. Read-only; forecasts older than 24h are marked stale.
      </p>
      {/* equal-height rows so every card is the same size; off while one is expanded */}
      <div className={cn("grid md:grid-cols-2 gap-6", !expanded && "auto-rows-fr")}>
        {isLoading && <div className="text-sm text-muted">Loading…</div>}
        {ENABLED_MODELS.map((m) => {
          const Model = COMPONENTS[m.id];
          return (
            <CardBoundary key={m.id} name={m.name}>
              <Model expanded={expanded === m.id} onToggle={() => toggle(m.id)} />
            </CardBoundary>
          );
        })}
      </div>
    </div>
  );
}
