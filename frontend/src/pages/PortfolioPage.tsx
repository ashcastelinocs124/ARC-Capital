import { useEquityCurve, usePortfolioMetrics, usePositions, useRecentFills } from "@/hooks/usePortfolio";
import { KpiCard } from "@/components/KpiCard";
import { PositionsTable } from "@/components/PositionsTable";
import { EquityCurveChart } from "@/components/EquityCurveChart";
import { RecentFills } from "@/components/RecentFills";
import { CounterPill } from "@/components/ui/filter-pills";

export default function PortfolioPage() {
  const { data: metrics = [] } = usePortfolioMetrics();
  const { data: positions = [] } = usePositions();
  const { data: equityCurve } = useEquityCurve();
  const { data: fills = [] } = useRecentFills();

  // Hero strip data
  const longCount = positions.filter((p) => p.side === "LONG").length;
  const shortCount = positions.filter((p) => p.side === "SHORT").length;
  const totalUnrealized = positions.reduce((s, p) => s + p.unrealized_pnl, 0);

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto">
      {/* Hero counter strip — Decasonic-style pill row */}
      <div className="flex items-center gap-2 flex-wrap">
        <h2 className="text-base font-semibold text-text mr-3">Portfolio</h2>
        <CounterPill label="Open Positions" count={positions.length} accent="default" />
        <CounterPill label="Long" count={longCount} accent="success" />
        <CounterPill label="Short" count={shortCount} accent="danger" />
        <CounterPill
          label="Unrealized P&L"
          count={
            totalUnrealized >= 0
              ? `+$${Math.abs(totalUnrealized).toFixed(0)}`
              : `-$${Math.abs(totalUnrealized).toFixed(0)}`
          }
          accent={totalUnrealized >= 0 ? "success" : "danger"}
        />
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {metrics.map((m, i) => (
          <KpiCard key={i} tile={m} />
        ))}
      </div>

      {/* Positions table */}
      <PositionsTable positions={positions} />

      {/* Equity + recent fills */}
      <div className="grid lg:grid-cols-2 gap-6">
        <EquityCurveChart data={equityCurve} />
        <RecentFills fills={fills} />
      </div>
    </div>
  );
}
