import { usd, qShort, type AiCapex } from "@/api/aiCapex";
import { C } from "@/lib/theme";
import { Chapter, Unavailable } from "./Chapter";
import { ChartTitle, GuidanceRows, Legend, StackedBars } from "./charts";

export function Spending({ data }: { data: AiCapex }) {
  const hyp = data.companies.filter((c) => c.kind === "hyperscaler");
  const tq = data.totals.quarters ?? [];
  const labels = tq.map((t) => t.q);
  const series = hyp.map((c) => {
    const by = new Map(c.quarters.map((q) => [q.q, q.capex]));
    return { key: c.ticker, name: c.name, color: C.co[c.ticker] ?? C.muted, values: labels.map((l) => by.get(l) ?? null) };
  });
  const guided = hyp.filter((c) => c.guidance);
  return (
    <Chapter
      id="spending" n="01" tag="SPENDING" question="How much are they spending?" sentence={data.sentences.spending}
      note="Capex here is cash paid for property and equipment, the same definition for every company. Guidance is as each company states it, for the year it covers."
    >
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="min-w-0">
          <ChartTitle>Quarterly capex, $bn</ChartTitle>
          {labels.length ? (
            <>
              <StackedBars
                labels={labels.map(qShort)}
                series={series}
                totals={tq.map((t) => ({ total: t.capex, note: t.reported < t.of ? `${t.reported} of ${t.of}` : undefined }))}
                label={`Quarterly capex of ${hyp.map((c) => c.name).join(", ")} from ${qShort(labels[0])} to ${qShort(labels[labels.length - 1])}, rising to ${usd(tq[tq.length - 1].capex)}`}
              />
              <Legend items={hyp.map((c) => [c.name, C.co[c.ticker] ?? C.muted])} />
            </>
          ) : <Unavailable what="SEC filings" />}
        </div>
        <div className="min-w-0">
          <ChartTitle>Last full year vs latest guidance, $bn</ChartTitle>
          {guided.length ? (
            <GuidanceRows
              rows={guided.map((c) => {
                const g = c.guidance!;
                const text = g.low == null ? "No full-year figure"
                  : `${g.high != null && g.high !== g.low ? `${usd(g.low)}–${usd(g.high)}` : `~${usd(g.low)}`} · ${g.label}`;
                return { name: c.name, color: C.co[c.ticker] ?? C.muted, actual: g.actual, low: g.low, high: g.high, text };
              })}
              label={`Capex guidance: ${guided.map((c) => `${c.name} ${c.guidance!.low != null ? usd(c.guidance!.low) : "no full-year figure"}`).join(", ")}`}
            />
          ) : <Unavailable what="earnings calls (cited search)" />}
          {guided.some((c) => c.guidance!.low == null) && (
            <p className="text-xs text-muted mt-1">
              {guided.filter((c) => c.guidance!.low == null).map((c) => `${c.name}: "${c.guidance!.line}"`).join(" ")}
            </p>
          )}
        </div>
      </div>
    </Chapter>
  );
}
