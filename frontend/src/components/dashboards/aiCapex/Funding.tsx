import { qName, usd, type AiCapex } from "@/api/aiCapex";
import { C } from "@/lib/theme";
import { Chapter, SourceLink, Unavailable } from "./Chapter";
import { ChartTitle, ChartWidth, DotRows, HBars, Legend, MIX_PARTS, Mix100, SMALLER } from "./charts";

const short = (d: string) => {
  const [y, m] = d.split("-");
  return m ? `${new Date(Number(y), Number(m) - 1).toLocaleDateString("en-US", { month: "short" })} '${y.slice(2)}` : d;
};

export function Funding({ data }: { data: AiCapex }) {
  const cos = data.companies;
  const color = (t: string) => C.co[t] ?? C.muted;
  const cents = cos.filter((c) => c.cents_per_dollar != null);
  const ocf = cos.filter((c) => c.ttm?.capex != null);
  const mixed = cos.filter((c) => c.mix);
  const deals = cos.flatMap((c) => c.borrowing.map((b) => ({ ...b, name: c.name, ticker: c.ticker })));
  const off = cos.flatMap((c) => c.off_balance.map((o) => ({ ...o, name: c.name })));
  const r = data.rates;
  return (
    <Chapter
      id="funding" n="02" tag="FUNDING" question="Can they afford it, and who's lending?" sentence={data.sentences.funding}
      note="The funding mix covers the last four quarters: each source's share of all the cash that came in. The rates are what each company paid on new borrowing this year."
    >
      {/* drawn smaller than the other sections, like 01 (user, Oct 28) */}
      <ChartWidth value={SMALLER}>
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="min-w-0">
          <ChartTitle>Capex per $1 of revenue, latest quarter</ChartTitle>
          {cents.length ? (
            <HBars
              rows={cents.map((c) => {
                const q = c.quarters[c.quarters.length - 1];
                return {
                  name: c.name, value: c.cents_per_dollar, ghost: c.cents_year_ago, color: color(c.ticker),
                  tip: {
                    title: `${c.name} · ${q ? qName(q.q) : "latest quarter"}`,
                    lines: [
                      `${c.cents_per_dollar}¢ of capex for every $1 of revenue`,
                      ...(q?.capex != null && q?.revenue != null ? [`${usd(q.capex)} of capex on ${usd(q.revenue)} of revenue`] : []),
                      ...(c.cents_year_ago != null ? [`A year ago: ${c.cents_year_ago}¢`] : []),
                    ],
                  },
                };
              })}
              max={Math.min(400, Math.max(100, ...cents.map((c) => c.cents_per_dollar!)))}
              fmt={(v) => `${v}¢`}
              ghostLabel="a year ago"
              label={`Capex per dollar of revenue: ${cents.map((c) => `${c.name} ${c.cents_per_dollar} cents`).join(", ")}`}
            />
          ) : <Unavailable what="SEC filings" />}
        </div>
        <div className="min-w-0">
          <ChartTitle>Capex ÷ the cash the business brings in, last four quarters</ChartTitle>
          {ocf.length ? (
            <HBars
              rows={ocf.map((c) => ({
                name: c.name, value: c.ocf_share, color: color(c.ticker),
                tip: {
                  title: `${c.name} · last four quarters`,
                  lines: [
                    c.ocf_share != null ? `Capex was ${c.ocf_share.toLocaleString()}% of the cash its business brought in` : "Its business used cash, so the ratio isn't meaningful",
                    ...(c.ttm.capex != null && c.ttm.ocf != null ? [`Capex ${usd(c.ttm.capex)} · operating cash ${usd(c.ttm.ocf)}`] : []),
                  ],
                },
              }))}
              max={Math.min(700, Math.max(200, ...ocf.map((c) => c.ocf_share ?? 0)))}
              fmt={(v) => `${v.toLocaleString()}%`}
              refLine={{ at: 100, label: "100% = all of it" }}
              label={`Capex as a share of operating cash: ${ocf.map((c) => `${c.name} ${c.ocf_share ?? "not meaningful"}${c.ocf_share != null ? " percent" : ""}`).join(", ")}`}
            />
          ) : <Unavailable what="SEC filings" />}
          <p className="text-xs text-muted mt-1">Past the dashed line, capex is more than the business brings in, so it's paid for with savings, debt or shares. "n/m" = the business used cash.</p>
        </div>
        <div className="min-w-0">
          <ChartTitle>Where the cash for capex came from, last four quarters</ChartTitle>
          <Legend items={MIX_PARTS.map(([, n, c]) => [n, c])} />
          {mixed.length ? (
            <Mix100
              rows={mixed.map((c) => ({ name: c.name, mix: c.mix! }))}
              label={`Funding mix: ${mixed.map((c) => `${c.name} ${c.mix!.own_cash} percent own cash, ${c.mix!.debt + c.mix!.convertible} percent debt`).join("; ")}`}
            />
          ) : <Unavailable what="SEC filings" />}
        </div>
        <div className="min-w-0">
          <ChartTitle>Rate on new borrowing this year (cited)</ChartTitle>
          {deals.length ? (
            <>
              <DotRows
                rows={deals.map((d) => ({
                  name: d.name, sub: `${d.label}${d.date ? `, ${short(d.date)}` : ""}`, value: d.rate_pct, color: color(d.ticker),
                  tip: {
                    title: `${d.name} · ${d.label}`,
                    lines: [
                      `${d.rate_pct}%${d.date ? `, ${short(d.date)}` : ""}`,
                      ...(/convertible/i.test(d.label) ? ["A convertible: low coupon because it can turn into shares"] : []),
                      ...(r ? [`For scale, today: 10-yr Treasury ${r.treasury_10y.value}%, high-yield ${r.high_yield.value}%`] : []),
                      `Source: ${d.source.title}`,
                    ],
                  },
                }))}
                refs={r ? [{ at: r.treasury_10y.value, label: `10-yr Treasury ${r.treasury_10y.value}%` }, { at: r.high_yield.value, label: `High-yield bonds ${r.high_yield.value}%` }] : []}
                label={`Rates on new borrowing: ${deals.map((d) => `${d.name} ${d.label} ${d.rate_pct} percent`).join(", ")}`}
              />
              <p className="text-xs text-muted mt-1">
                Convertible notes pay little because buyers can swap them for shares. Sources:{" "}
                {[...new Map(deals.map((d) => [d.name, d.source.url])).entries()].map(([name, url], i) => (
                  <span key={name}>{i > 0 && " · "}<SourceLink title={name} url={url} /></span>
                ))}
              </p>
            </>
          ) : <Unavailable what="earnings calls and filings (cited search)" />}
        </div>
      </div>
      </ChartWidth>
      {off.length > 0 && (
        <>
          <div className="eyebrow mt-5 mb-1.5">Funding outside the balance sheet</div>
          <div className="grid gap-2.5 sm:grid-cols-3">
            {off.map((o, i) => (
              <div key={i} className="rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[12.5px] leading-[18px] text-text-2">
                {o.name}
                <b className="num block text-[18px] text-text my-0.5"><SourceLink title={usd(o.value)} url={o.source.url} /></b>
                {o.label}
              </div>
            ))}
          </div>
        </>
      )}
    </Chapter>
  );
}
