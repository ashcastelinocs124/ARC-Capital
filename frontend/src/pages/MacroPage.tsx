import { useWeekAhead } from "@/hooks/useWeekAhead";
import { PageIntro } from "@/components/layout/PageIntro";
import { WeekMap } from "@/components/weekAhead/WeekMap";
import { InflationExpectations } from "@/components/weekAhead/InflationExpectations";
import { EpsGrowth } from "@/components/weekAhead/EpsGrowth";
import { OpenRouterBars, RampChart } from "@/components/weekAhead/AiSpend";
import { GapNote } from "@/components/weekAhead/Tooltip";
import { SectorValuation } from "@/components/weekAhead/SectorValuation";
import { C } from "@/lib/theme";

const span = (a: string, b: string) => {
  const f = (d: string) => new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${f(a)} – ${f(b)}`;
};

function Card({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className="bg-surface border border-border rounded-xl shadow-card px-4 py-4 md:px-5 min-w-0">
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <h2 className="text-[15px] font-semibold text-text">{title}</h2>
        {sub && <span className="text-xs text-muted text-right">{sub}</span>}
      </div>
      {children}
    </section>
  );
}

function Legend() {
  // shape doubles colour so the legend still reads without colour
  const items: [string, string, string][] = [
    ["Inflation", C.inflation, "50%"], ["Jobs", C.jobs, "2px"], ["Earnings", C.earnings, "50%"],
    ["AI launch", C.ai, "1px"], ["Other data", C.muted2, "50%"],
  ];
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-2 mb-1">
      {items.map(([n, c, r]) => (
        <span key={n} className="flex items-center gap-1.5">
          <i className="inline-block w-2.5 h-2.5" style={{ background: c, borderRadius: r, transform: n === "AI launch" ? "rotate(45deg)" : undefined }} />
          {n}
        </span>
      ))}
    </div>
  );
}

export default function MacroPage() {
  const { data, isLoading } = useWeekAhead();
  const reported = data?.events.filter((e) => e.kind === "ai" && e.status === "reported" && !(e.date && e.date <= data.week_end)) ?? [];
  const or = data?.spend.openrouter;
  return (
    <div className="p-4 md:p-8 space-y-6">
      <PageIntro kicker="Week Ahead" title="What's coming this week"
        when={data ? {
          label: "Week of",
          value: span(data.week_start, data.week_end),
          note: `updated ${new Date(data.generated_at).toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" })} ET`,
        } : undefined}>
        Inflation and jobs releases from the five largest economies, S&amp;P 500 and big AI-company earnings and AI model
        launches on one timeline, then what the market expects and where AI money is going. Refreshed each evening after the close.
      </PageIntro>
      {!data ? (
        <p className="text-sm text-muted">{isLoading ? "Loading…" : "No Week Ahead data yet."}</p>
      ) : (
        <>
          <Card title="The week on one line" sub="ET · bubble size = market cap · hover for estimates">
            <Legend />
            <WeekMap data={data} />
            {reported.length > 0 && (
              <p className="text-xs text-text-2 mt-2">
                Reported upcoming:{" "}
                {reported.map((e, i) => (
                  <span key={i}>
                    {i > 0 && " · "}
                    <a className="underline" href={e.source_url} target="_blank" rel="noreferrer">{e.name}</a> ({e.lab}, {e.when})
                  </span>
                ))}
              </p>
            )}
            <GapNote gaps={data.gaps} lanes={["econ", "earnings", "ai"]} />
          </Card>
          <div className="grid gap-6 md:grid-cols-2">
            <Card title="Inflation: previous → consensus" sub="y/y %"><InflationExpectations events={data.events} /></Card>
            <Card title="Expected EPS growth vs a year ago" sub="consensus EPS ÷ year-ago EPS"><EpsGrowth events={data.events} /></Card>
          </div>
          {data.sectors && data.sectors.length > 0 && (
            <Card title="Sectors: year-to-date vs valuation" sub="SPDR sector ETFs · YTD price return vs trailing P/E · hover for details">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-2 mb-1">
                <span className="flex items-center gap-1.5"><i className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: C.earnings }} />Earnings growing (median of top 10)</span>
                <span className="flex items-center gap-1.5"><i className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: C.danger }} />Earnings shrinking</span>
                <span className="flex items-center gap-1.5"><i className="inline-block w-2.5 h-2.5 rounded-full border-2" style={{ borderColor: C.text }} />S&amp;P 500 (SPY)</span>
              </div>
              <SectorValuation rows={data.sectors} />
              <p className="text-[11.5px] text-muted mt-2">
                The dashed lines through the S&amp;P 500 split the chart. A red dot high up means the price ran ahead of shrinking
                earnings. Earnings growth is the median latest-quarter year-on-year growth of each sector's 10 largest companies.
              </p>
              <GapNote gaps={data.gaps} lanes={["sectors"]} />
            </Card>
          )}
          <div className="grid gap-6 md:grid-cols-2">
            <Card title="Businesses paying for AI" sub="Ramp AI Index via FRED · % of US businesses · monthly">
              <RampChart ramp={data.spend.ramp} />
              <p className="text-[11.5px] text-muted mt-2">
                "Any AI" is the share of US businesses on Ramp that paid for at least one AI product that month, from any
                vendor. Many pay more than one provider, so the provider lines add up to more than it.
              </p>
              <GapNote gaps={data.gaps} lanes={["ramp"]} />
            </Card>
            <Card title="Who developers' tokens go to" sub={or ? `OpenRouter · ${or.basis} · ${span(or.week[0], or.week[1])}` : "OpenRouter"}>
              <OpenRouterBars or={or ?? null} />
              <p className="text-[11.5px] text-muted mt-2">Developer traffic routed through OpenRouter, not total market spend.</p>
              <GapNote gaps={data.gaps} lanes={["openrouter"]} />
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
