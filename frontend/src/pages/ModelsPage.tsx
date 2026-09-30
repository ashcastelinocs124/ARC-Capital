import { useState } from "react";
import { useModels } from "@/hooks/useModels";
import type { ModelCard } from "@/api/endpoints";
import { cn } from "@/lib/cn";
import { EconomicReleasesCard } from "@/components/EconomicReleasesCard";

const WEAK_ACCURACY = 0.55; // near coin-flip for a binary up/down call
const MAX_DATA_LAG_MONTHS = 3;

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

function Card({ card }: { card: ModelCard }) {
  const [open, setOpen] = useState(false);

  const header = (
    <div className="flex items-start justify-between gap-3">
      <div>
        <div className="text-base font-semibold text-text">{card.name}</div>
        <div className="text-xs text-muted">{card.kind}</div>
      </div>
      <Badge card={card} />
    </div>
  );

  if (card.status === "missing") {
    return (
      <div className="card p-5">
        {header}
        <div className="text-center text-sm text-muted py-9">No forecast on disk yet.</div>
      </div>
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
    <div className="card p-5">
      {header}

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

      {!!card.features?.length && (
        <div className="mt-3.5 border-t border-border pt-3">
          <button onClick={() => setOpen(!open)} className="text-xs font-medium text-accent hover:text-accent-hover">
            {open ? "Hide" : "Show"} {card.features.length} features {open ? "▴" : "▾"}
          </button>
          {open && (
            <div className="flex flex-wrap gap-1.5 mt-2.5">
              {card.features.map((f) => (
                <span key={f} className="font-mono text-xs bg-surface-2 border border-border rounded-md px-1.5 py-0.5">
                  {f}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ModelsPage() {
  const { data: cards = [], isLoading } = useModels();

  return (
    <div className="p-8 space-y-5">
      <div>
        <h2 className="text-base font-semibold text-text">Models</h2>
        <p className="text-xs text-muted mt-0.5">
          Current state of the XGBoost forecasters feeding the pipeline. Read-only; forecasts older than 24h are
          marked stale.
        </p>
      </div>
      {isLoading ? (
        <div className="text-sm text-muted">Loading…</div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {cards.map((c) => (
            <Card key={c.id} card={c} />
          ))}
        </div>
      )}
      <EconomicReleasesCard subtitle="inputs the growth and inflation models read, from the latest Daily Update" />
    </div>
  );
}
