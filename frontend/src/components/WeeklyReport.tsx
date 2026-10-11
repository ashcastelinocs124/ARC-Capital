import type { WeeklyRecord, WeeklyScoreRow } from "@/api/endpoints";
import { cn } from "@/lib/cn";

// Same path in dev (vite proxies /api) and on the static site (export_snapshot copies the PNGs).
const chartUrl = (rec: WeeklyRecord, file: string) =>
  `/api/weekly/${rec.week}/charts/${file}?v=${encodeURIComponent(rec.generated_at)}`;
const LONG = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const SHORT = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const d = (s: string) => new Date(`${s}T00:00:00Z`);

function chg(v: number | null, unit: "%" | "bp") {
  if (v === null) return <span className="text-muted">–</span>;
  const s = unit === "bp" ? `${v > 0 ? "+" : ""}${v.toFixed(0)}bp` : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
  return <span className={v > 0 ? "text-success" : v < 0 ? "text-danger" : ""}>{s}</span>;
}

const level = (r: WeeklyScoreRow) =>
  r.unit === "%" ? `${r.level.toFixed(2)}%`
    : r.unit === "$" ? `$${r.level.toFixed(2)}`
    : r.level.toLocaleString("en-US", { maximumFractionDigits: 2 });

function Page({ n, children, header }: { n: number; children: React.ReactNode; header?: string }) {
  return (
    <section className="weekly-page relative bg-surface shadow-card px-5 py-6 md:px-10 md:pt-8 md:pb-8 mb-4">
      {header && (
        <div className="flex items-center gap-1.5 text-[11px] text-muted border-b border-border pb-1.5 mb-4">
          <img src="/arc-logo.png" alt="" className="logo-img h-4 w-auto" />{header}
        </div>
      )}
      {children}
      <div className="absolute right-6 bottom-2 text-[10.5px] text-muted">{n}</div>
    </section>
  );
}

const Dot = () => <span className="absolute left-0 top-[7px] h-1.5 w-1.5 bg-accent" />;
const Num = ({ n }: { n: number }) => (
  <span className="absolute left-0 top-[1px] h-[18px] w-[18px] rounded-sm bg-accent-soft text-accent text-[10.5px] font-bold flex items-center justify-center">{n}</span>
);

/** The Weekly Deep Dive as report pages: page 1 the week at a glance, then one trend per page. */
export function WeeklyReport({ rec }: { rec: WeeklyRecord }) {
  const r = rec.report;
  const header = `Weekly Deep Dive · ${LONG.format(d(rec.end))}`;
  const challenged = (name: string) => rec.grill_log.filter((g) => g.agent === name).length;
  // a desk that failed returned no findings: it isn't part of this report's desk
  const desks = rec.plan.agents.filter((a) => rec.findings.some((f) => f.agent === a.name));
  // The Editor writes sections in the Lead's trend order, so a trend's number is its position.
  const trendNo = (title: string) => rec.plan.trends.findIndex((t) => t.title === title) + 1;
  const short = (t: string) => (t.length > 28 ? `${t.slice(0, 27).trimEnd()}…` : t);
  const lead = rec.exhibits.find((e) => e.section === 0);
  const facts = Object.fromEntries(rec.facts.map((f) => [f.id, f]));
  const cited = [...new Set([...r.sections.flatMap((s) => s.fact_ids), ...r.bullets.flatMap((b) => b.fact_ids)])]
    .map((id) => facts[id]).filter(Boolean);
  const sources = [...new Map(cited.map((f) => [f.source_url, f.source_title])).entries()];
  const counts: [string, number][] = [
    ["Morning Notes read", rec.counts.notes], ["Specialist agents", rec.counts.agents],
    ["Data pulls", rec.counts.data_pulls], ["Board posts shared", rec.counts.board_posts],
    ["Grill rounds", rec.counts.grill_rounds], ["Figures checked", rec.counts.figures_checked],
    ["Exhibits", rec.counts.exhibits],
  ];
  const methodPage = r.sections.length + 2;
  return (
    <article>
      <Page n={1}>
        <div className="flex justify-between items-start mb-5">
          <img src="/arc-logo.png" alt="ARC Research" className="logo-img h-11 w-auto" />
          <div className="text-right text-[12.5px] leading-[18px] font-semibold text-accent">
            Weekly Deep Dive<div className="font-normal text-muted">{LONG.format(d(rec.end))}</div>
          </div>
        </div>
        <div className="grid gap-7 md:grid-cols-[1fr_250px]">
          <div className="min-w-0">
            <h2 className="font-serif font-bold text-[26px] md:text-[30px] leading-[1.12] text-accent">{r.title}</h2>
            <div className="text-[15px] text-text-2 mt-2.5 mb-4">
              Week {rec.week.split("-W")[1]} ({SHORT.format(d(rec.start))}–{SHORT.format(d(rec.end))}): {r.subtitle}
            </div>
            <ol className="space-y-2">
              {r.bullets.map((b, i) => (
                <li key={b.lead} className="relative pl-7 text-[12.8px] leading-[19px] text-text-2">
                  <Num n={i + 1} /><b className="text-text">{b.lead}</b> {b.body}
                </li>
              ))}
            </ol>
            <p className="relative pl-4 mt-3 text-[12.8px] leading-[19px] text-text-2">
              <Dot /><b className="text-text">What to watch next week.</b> {r.watch}
            </p>
          </div>
          <aside className="space-y-3 text-xs">
            {rec.regime.pulse !== null && (
              <div className="border-b border-border pb-3">
                <div className="text-[11px] text-muted">ARC regime read (from /models)</div>
                <div className="text-text-2 leading-[18px] mt-1">
                  Pulse P(expansion) {rec.regime.pulse}%<br />Pressure P(CPI accelerates) {rec.regime.pressure}%
                </div>
              </div>
            )}
            <div className="border-b border-border pb-3">
              <div className="font-semibold text-[12.5px] mb-1.5">Research desk · {desks.length} desks</div>
              {desks.map((a) => (
                <div key={a.name} className="mb-2 leading-[17px]">
                  <b className="block">{a.name}</b>
                  <span className="text-muted text-[11px]">
                    {rec.models.agents ?? ""}{rec.models.agents ? " · " : ""}challenged {challenged(a.name)}×
                  </span>
                  {!!a.trends?.length && (
                    <div className="mt-0.5 flex flex-wrap gap-1">
                      {a.trends.map((t) => (
                        <span key={t} title={t} className="border border-border-strong rounded-sm px-1 text-[10.5px] text-text-2">
                          {trendNo(t) ? `${trendNo(t)} ` : ""}{short(t)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div className="leading-[17px]">
                <b className="block">Deep Editor</b>
                <span className="text-muted text-[11px]">{rec.models.editor ?? "Claude Opus 5.5"}</span>
              </div>
            </div>
            {lead && <img src={chartUrl(rec, lead.file)} alt={lead.title} className="w-full" />}
          </aside>
        </div>
        <div className="grid gap-7 md:grid-cols-[1fr_250px] mt-5 border-t-2 border-text pt-2">
          <div className="min-w-0">
            <div className="text-xs font-bold mb-1">The week in markets</div>
            <table className="w-full text-[11.5px] num">
              <thead>
                <tr className="bg-[#1f2937] text-white">
                  {["Asset", "Level", "1w", "1m", "3m", "YTD"].map((h, i) => (
                    <th key={h} className={cn("px-1.5 py-1 font-semibold", i ? "text-right" : "text-left")}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rec.scorecard.map((s) => (
                  <tr key={s.asset} className="border-b border-border">
                    <td className="px-1.5 py-1">{s.asset}</td>
                    <td className="px-1.5 text-right">{level(s)}</td>
                    {(["w1", "m1", "m3", "ytd"] as const).map((k) => (
                      <td key={k} className="px-1.5 text-right">{chg(s[k], s.change_unit)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="text-[10.5px] text-muted mt-1">
              Source: ARC Research. Data: Yahoo Finance, FRED. Close {LONG.format(d(rec.end))}.
            </div>
          </div>
          <div>
            <div className="text-xs font-bold mb-1">How this report was made</div>
            <table className="w-full text-[11.5px] num">
              <tbody>
                {counts.map(([k, v]) => (
                  <tr key={k} className="border-b border-border"><td className="py-1">{k}</td><td className="text-right">{v}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="border-t border-border mt-4 pt-2 text-[11px] text-text-2">
          <b className="block">See page {methodPage} for method, data sources and limitations.</b>
          Written by ARC Research's AI research desk. Every figure is checked against cited data. Not investment advice.
        </div>
      </Page>

      {r.sections.map((s, i) => (
        <Page key={s.title} n={i + 2} header={`${header} · Trend ${i + 1} of ${r.sections.length}`}>
          <h2 className="font-serif font-bold text-[21px] text-accent border-b-[3px] border-accent pb-1.5 mb-4">
            {i + 1}. {s.title}
          </h2>
          <div className="grid gap-7 md:grid-cols-2">
            <div className="min-w-0">
              <div className="text-[10.5px] font-bold text-muted tracking-wider mb-1.5">
                <span className="border border-border-strong px-1.5 rounded-sm text-text-2">{s.agent.toUpperCase()}</span>
              </div>
              {s.paragraphs.map((p) => <p key={p} className="text-[13px] leading-[20.5px] text-text-2 mb-2.5">{p}</p>)}
              {s.challenges.map((c) => (
                <div key={c.question}
                  className="border border-dashed border-warning bg-warning-soft/40 rounded-md px-3 py-2 text-xs leading-[18px] text-text-2 mt-1.5">
                  <b className="block text-[10.5px] uppercase tracking-wider text-warning">Editor challenged</b>
                  “{c.question}” {c.answer} <i>{c.verdict}</i>
                </div>
              ))}
            </div>
            <div>
              {rec.exhibits.filter((e) => e.section === i).map((e) => (
                <figure key={e.file} className="border-t-2 border-text pt-1.5 mb-4">
                  <img src={chartUrl(rec, e.file)} alt={`${e.title}. ${e.subtitle}`} className="w-full" loading="lazy" />
                </figure>
              ))}
            </div>
          </div>
        </Page>
      ))}

      <Page n={methodPage} header={`${header} · Method & sources`}>
        <h2 className="font-serif font-bold text-[21px] text-accent border-b-[3px] border-accent pb-1.5 mb-4">Method and sources</h2>
        <p className="text-[13px] leading-[20.5px] text-text-2 mb-3">
          A Lead agent ({rec.models.lead ?? "OpenAI"}) read the week's Morning Notes, picked the trends and staffed up to four
          specialist desks ({rec.models.agents ?? "OpenAI"}). Each desk pulled its own data through tools that turn every
          result into a numbered fact, and shared facts with related desks on a board. The Deep Editor
          ({rec.models.editor ?? "Claude Opus 5.5"}) challenged every desk's findings before writing. A number guard
          checks that every %, bp and pp figure appears in the facts each part of the report cites.
        </p>
        <ul className="text-xs space-y-1 mb-3">
          {sources.map(([url, title]) => (
            <li key={url}><a href={url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{title}</a></li>
          ))}
        </ul>
        {rec.data_gaps.length > 0 && <p className="text-[11px] text-muted">Data gaps: {rec.data_gaps.join("; ")}.</p>}
        <p className="text-[11px] text-muted mt-2">Not investment advice.</p>
      </Page>
    </article>
  );
}
