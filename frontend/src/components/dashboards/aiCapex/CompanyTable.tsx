import { usd, type AiCapex, type CapexCompany } from "@/api/aiCapex";
import { company } from "@/lib/company";
import { C } from "@/lib/theme";
import { SourceLink } from "./Chapter";

const dash = <span className="text-muted">—</span>;

function Row({ c }: { c: CapexCompany }) {
  const q = c.quarters[c.quarters.length - 1];
  const debt = c.mix ? c.mix.debt + c.mix.convertible : null;
  const g = c.guidance;
  return (
    <tr className="border-t border-border">
      <th scope="row" className="py-2 pr-3 text-left font-medium text-text whitespace-nowrap">
        <i className="inline-block w-2.5 h-2.5 rounded-sm mr-2 align-baseline" style={{ background: C.co[c.ticker] ?? C.muted }} aria-hidden />
        {company(c.name, c.ticker)}
      </th>
      <td className="num text-right px-2">{q?.capex != null ? usd(q.capex) : dash}</td>
      <td className="num text-right px-2">{c.yoy_pct != null ? <span className={c.yoy_pct >= 0 ? "text-accent" : "text-danger"}>{c.yoy_pct >= 0 ? "▲" : "▼"} {Math.abs(c.yoy_pct)}%</span> : dash}</td>
      <td className="num text-right px-2">{c.cents_per_dollar != null ? <>{c.cents_per_dollar}¢{c.cents_year_ago != null && <span className="text-muted"> ({c.cents_year_ago}¢)</span>}</> : dash}</td>
      <td className={`num text-right px-2 ${c.ocf_share != null && c.ocf_share > 100 ? "text-danger" : ""}`}>{c.ocf_share != null ? `${c.ocf_share.toLocaleString()}%` : "n/m"}</td>
      <td className="num text-right px-2">{debt != null ? `${debt}%${c.mix!.convertible > c.mix!.debt ? " conv." : ""}` : dash}</td>
      <td className="num text-right px-2">{c.avg_rate != null ? `${c.avg_rate}%` : dash}</td>
      <td className="num text-right px-2">{c.backlog ? usd(c.backlog.value) : c.kind === "hyperscaler" && !c.cloud ? <span className="text-muted">no cloud</span> : dash}</td>
      <td className="num text-right pl-2 whitespace-nowrap">
        {g && g.low != null ? (
          <SourceLink title={`${g.high != null && g.high !== g.low ? `${usd(g.low)}–${usd(g.high)}` : `~${usd(g.low)}`}`} url={g.source.url} />
        ) : dash}
        {g?.label && <span className="block text-[10.5px] text-muted">{g.label}</span>}
      </td>
    </tr>
  );
}

export function CompanyTable({ data }: { data: AiCapex }) {
  const groups: [string, CapexCompany[]][] = [
    ["Hyperscalers", data.companies.filter((c) => c.kind === "hyperscaler")],
    ["Neoclouds", data.companies.filter((c) => c.kind === "neocloud")],
  ];
  const cols = ["Capex, latest quarter", "vs a year ago", "Per $1 of revenue", "÷ operating cash", "Debt-funded", "Avg rate on debt", "Backlog", "Latest guidance"];
  return (
    <section aria-labelledby="table-h" className="bg-surface border border-border rounded-xl shadow-card px-4 py-4 md:px-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
        <div>
          <div className="eyebrow">For repeat readers</div>
          <h2 id="table-h" className="text-[16px] font-semibold text-text">Every company, one row each</h2>
        </div>
        <span className="text-xs text-muted">Underlined figures link to their cited source</span>
      </div>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-[11px] uppercase tracking-[0.05em] text-muted">
            <th scope="col" className="text-left font-semibold py-1">Company</th>
            {cols.map((c) => <th key={c} scope="col" className="text-right font-semibold px-2 whitespace-nowrap">{c}</th>)}
          </tr>
        </thead>
        {groups.map(([name, rows]) => (
          <tbody key={name}>
            <tr><td colSpan={9} className="pt-3 pb-1 text-[11px] font-bold uppercase tracking-[0.06em] text-accent">{name}</td></tr>
            {rows.map((c) => <Row key={c.ticker} c={c} />)}
          </tbody>
        ))}
      </table>
      <p className="text-xs text-muted mt-2">
        (¢) = a year ago. Red = capex above the cash the business brings in (last four quarters). Debt-funded = new
        debt and convertible notes as a share of all the cash that came in over the last four quarters; "conv." =
        mostly convertible notes. The average rate counts interest on debt and finance leases.
      </p>
    </section>
  );
}
