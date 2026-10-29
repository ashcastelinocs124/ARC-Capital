import { usd, type AiCapex } from "@/api/aiCapex";
import { C } from "@/lib/theme";
import { Chapter, Unavailable } from "./Chapter";
import { ChartTitle, Dumbbell, HBars } from "./charts";
import { change } from "./hover";

export function Demand({ data }: { data: AiCapex }) {
  const hyp = data.companies.filter((c) => c.kind === "hyperscaler");
  const backlog = hyp.filter((c) => c.backlog);
  const cloud = hyp.filter((c) => c.cloud?.growth_pct != null);
  return (
    <Chapter
      id="demand" n="03" tag="DEMAND" question="Is the demand there?" sentence={data.sentences.demand}
      note="Backlog is revenue customers have signed for but not yet received, as each company headlines it. A large share of Microsoft's and Oracle's backlog is OpenAI."
    >
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="min-w-0">
          <ChartTitle>Contracted backlog: a year ago → latest</ChartTitle>
          {backlog.length ? (
            <Dumbbell
              rows={backlog.map((c) => {
                const b = c.backlog!;
                const grew = change(b.value, b.year_ago);
                return {
                  name: c.name, color: C.co[c.ticker] ?? C.muted, from: b.year_ago, to: b.value, fmt: usd(b.value),
                  tip: {
                    title: `${c.name} · ${b.label}`,
                    lines: [
                      `${usd(b.value)} signed but not yet delivered`,
                      ...(b.year_ago != null ? [`A year ago ${usd(b.year_ago)} (${grew})`] : ["No year-ago figure"]),
                      ...(c.ttm?.revenue ? [`${(b.value / c.ttm.revenue).toFixed(1)} years of its last four quarters' revenue`] : []),
                    ],
                  },
                };
              })}
              label={`Backlog: ${backlog.map((c) => `${c.name} ${usd(c.backlog!.value)}${c.backlog!.year_ago ? `, from ${usd(c.backlog!.year_ago)} a year ago` : ""}`).join("; ")}`}
            />
          ) : <Unavailable what="earnings releases" />}
          {backlog.length > 0 && <p className="text-xs text-muted mt-1">{backlog.map((c) => `${c.name}: ${c.backlog!.label}`).join(" · ")}</p>}
        </div>
        <div className="min-w-0">
          <ChartTitle>Cloud revenue growth, from a year ago</ChartTitle>
          {cloud.length ? (
            <HBars
              rows={cloud.map((c) => ({
                name: c.cloud!.name.replace("Oracle Cloud Infrastructure", "Oracle OCI"), value: c.cloud!.growth_pct, color: C.co[c.ticker] ?? C.muted,
                tip: {
                  title: `${c.cloud!.name} (${c.name})`,
                  lines: [
                    `Revenue up ${c.cloud!.growth_pct}% on a year ago`,
                    ...(c.cloud!.revenue != null ? [`${usd(c.cloud!.revenue)} in the latest quarter`] : []),
                    "From the company's earnings release",
                  ],
                },
              }))}
              max={Math.max(50, ...cloud.map((c) => c.cloud!.growth_pct!)) * 1.1}
              fmt={(v) => `+${v}%`}
              label={`Cloud revenue growth: ${cloud.map((c) => `${c.cloud!.name} ${c.cloud!.growth_pct} percent`).join(", ")}`}
            />
          ) : <Unavailable what="earnings releases" />}
        </div>
      </div>
    </Chapter>
  );
}
