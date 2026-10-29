import { useSearchParams } from "react-router-dom";
import { qShort, usd, type AiCapex } from "@/api/aiCapex";
import { cn } from "@/lib/cn";
import { company } from "@/lib/company";
import { C } from "@/lib/theme";
import { Chapter, SourceLink, Unavailable } from "./Chapter";
import { Spark } from "./charts";

type Size = "all" | "large" | "mid" | "small";
const SIZES: [Size, string][] = [["all", "All"], ["large", "Large"], ["mid", "Mid"], ["small", "Small"]];
const SIZE_WORDS: Record<Size, string> = { all: "companies of all sizes", large: "large companies", mid: "mid-sized companies", small: "small companies" };
const CENSUS_SIZE: Record<Exclude<Size, "all">, string> = { large: "250+", mid: "50–249", small: "1–49" };
const PRODUCT_NAMES: Record<string, string> = { Anthropic: "Anthropic (Claude)", OpenAI: "OpenAI (ChatGPT)", xAI: "xAI (Grok)" };

/** Plain bars as a list: each row says its label and value in text, the bar only repeats it. */
function BarList({ rows, max, on }: { rows: { label: string; value: number }[]; max: number; on: (i: number) => boolean }) {
  return (
    <ul className="grid gap-1.5 text-[12px]">
      {rows.map((r, i) => (
        <li key={r.label} className="grid grid-cols-[minmax(0,7.5rem)_1fr_3.2rem] items-center gap-2">
          <span className={cn("truncate text-right", on(i) ? "text-text font-semibold" : "text-muted")}>{r.label}</span>
          <span className="h-2.5 rounded-sm bg-surface-3" aria-hidden>
            <span className="block h-full rounded-sm" style={{ width: `${Math.min(100, (r.value / max) * 100)}%`, background: on(i) ? C.accent : C.borderStrong }} />
          </span>
          <span className="num text-text-2 font-semibold">{r.value}%</span>
        </li>
      ))}
    </ul>
  );
}

function Panel({ eyebrow, title, src, children }: { eyebrow: string; title: string; src: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3.5 min-w-0" aria-live="polite">
      <div className="eyebrow">{eyebrow}</div>
      <h3 className="text-[14.5px] font-semibold text-text mt-0.5">{title}</h3>
      <div className="text-[11px] text-muted mb-2.5">{src}</div>
      {children}
    </div>
  );
}

const Note = ({ children }: { children: React.ReactNode }) => (
  <p className="mt-2.5 rounded-md border-l-2 border-warning bg-warning-soft px-2.5 py-1.5 text-xs leading-[17px] text-text">{children}</p>
);
// pressed = solid accent (passes 4.5:1 in both themes); the focus ring is inset so no parent clips it
const FOCUS = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent";

export function Adoption({ data }: { data: AiCapex }) {
  const [params, setParams] = useSearchParams();
  const vendors = data.ramp?.vendors ?? [];
  const rawSize = params.get("size") as Size | null;
  const size: Size = SIZES.some(([s]) => s === rawSize) ? rawSize! : "all"; // a bad shared link reads as All
  const rawProduct = params.get("product");
  const product = vendors.some((v) => v.vendor === rawProduct) ? rawProduct! : "all";
  const set = (k: "size" | "product", v: string) => {
    const next = new URLSearchParams(params);
    if (v === "all") next.delete(k);
    else next.set(k, v);
    setParams(next, { replace: true, preventScrollReset: true });
  };

  const ramp = data.ramp;
  const rampSize = size !== "all" ? ramp?.sizes.find((s) => s.size === size) : undefined;
  const vendor = vendors.find((v) => v.vendor === product);
  const arc = data.adoption?.buckets[size];
  const census = data.census;
  const classes = census?.by_class.filter((c) => size === "all" || c.bucket === size) ?? [];
  // Census prints a share per size class, not per bucket: a bucket shows its classes' range, never an average
  const lo = classes.length ? Math.min(...classes.map((c) => c.pct)) : null;
  const hi = classes.length ? Math.max(...classes.map((c) => c.pct)) : null;
  const censusPct = size === "all" ? (census?.overall_pct != null ? `${census.overall_pct}%` : null)
    : lo == null ? null : lo === hi ? `${lo}%` : `${lo}–${hi}%`;
  const nv = data.nvidia;
  const nvLast = nv?.quarters[nv.quarters.length - 1];
  const or = data.openrouter;
  const tokens = or ? or.labs.reduce((s, l) => s + l.tokens, 0) / 1e12 : null;

  const lede = vendor
    ? `**${vendor.pct}%** of US businesses on Ramp pay ${PRODUCT_NAMES[vendor.vendor] ?? vendor.vendor}.${size !== "all" ? " Ramp doesn't split this by company size." : ""}`
    : [
        ramp && (rampSize ? `**${rampSize.pct}%** of ${rampSize.label.toLowerCase()} on Ramp pay for AI tools.` : ramp.sizes.length ? `Between **${Math.min(...ramp.sizes.map((s) => s.pct))}%** and **${Math.max(...ramp.sizes.map((s) => s.pct))}%** of US businesses on Ramp pay for AI tools, depending on size.` : ""),
        arc && arc.pct != null ? `**${arc.pct}%** of ${SIZE_WORDS[size]} in ARC's index (outside the companies above) make a concrete AI claim in their latest filing.` : "",
        censusPct != null ? `In the Census survey, **${censusPct}** of ${size === "all" ? "US firms" : `firms with ${CENSUS_SIZE[size]} employees, by size class,`} say they used AI in the last two weeks.` : "",
      ].filter(Boolean).join(" ");

  return (
    <Chapter
      id="adoption" n="05" tag="ADOPTION" question="Is demand spreading beyond the big buyers?" sentence={lede}
      note="Three separate reads: what companies pay for (Ramp), what they tell investors (ARC's AI Adoption Index, from SEC filings) and what they tell the Census Bureau. The hyperscalers, neoclouds and Nvidia are left out of ARC's index here."
    >
      <div className="grid gap-3 sm:grid-cols-2 mb-3.5">
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <div className="eyebrow">Nvidia data center sales</div>
          {nvLast?.value != null ? (
            <>
              <div className="num text-[22px] font-bold mt-1">{usd(nvLast.value)}{nv!.growth_pct != null && <span className={cn("text-[13px] ml-1.5", nv!.growth_pct >= 0 ? "text-accent" : "text-danger")}>{nv!.growth_pct >= 0 ? "▲" : "▼"} {Math.abs(nv!.growth_pct)}%</span>}</div>
              <div className="text-xs text-muted mb-1.5">Quarterly, {qShort(nv!.quarters[0].q)} → {qShort(nvLast.q)}</div>
              <Spark values={nv!.quarters.map((q) => q.value ?? 0)} label={`Nvidia data center sales by quarter, latest ${usd(nvLast.value)}`} />
            </>
          ) : <Unavailable what="Nvidia earnings releases" />}
        </div>
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <div className="eyebrow">Tokens served on OpenRouter</div>
          {or && tokens != null ? (
            <>
              <div className="num text-[22px] font-bold mt-1">{tokens.toFixed(1)}T <span className="text-xs font-normal text-muted">tokens, week to {or.week[1]}</span></div>
              <div className="text-xs text-muted">Its {or.basis}. Biggest lab: {or.labs[0]?.lab} ({or.labs[0]?.share}%).</div>
            </>
          ) : <Unavailable what="OpenRouter" />}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2.5 rounded-lg border border-border bg-surface-2 px-3.5 py-3 mb-3.5">
        <div className="flex items-center gap-2" role="group" aria-labelledby="f-size">
          <span id="f-size" className="eyebrow">Company size</span>
          <span className="inline-flex overflow-hidden rounded-lg border border-border-strong">
            {SIZES.map(([s, label]) => (
              <button key={s} type="button" aria-pressed={size === s} onClick={() => set("size", s)}
                className={cn("px-3 py-1.5 text-[13px] font-semibold border-l border-border-strong first:border-l-0", FOCUS,
                  size === s ? "bg-accent text-on-accent" : "bg-surface text-text-2 hover:text-text")}>{label}</button>
            ))}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-labelledby="f-product">
          <span id="f-product" className="eyebrow">AI product</span>
          {[["all", "All products"] as const, ...vendors.map((v) => [v.vendor, PRODUCT_NAMES[v.vendor] ?? v.vendor] as const)].map(([v, label]) => (
            <button key={v} type="button" aria-pressed={product === v} onClick={() => set("product", v)}
              className={cn("rounded-full border px-3 py-1 text-[13px] font-semibold", FOCUS,
                product === v ? "border-accent bg-accent text-on-accent" : "border-border-strong bg-surface text-text-2 hover:text-text")}>{label}</button>
          ))}
        </div>
      </div>

      <div className="grid gap-3.5 lg:grid-cols-3">
        <Panel eyebrow="Paying for AI tools" title="Ramp AI Index" src={ramp ? <>Card and bill payments · {ramp.month} · monthly</> : "Ramp"}>
          {!ramp ? <Unavailable what="Ramp" /> : vendor ? (
            <>
              <BarList rows={vendors.map((v) => ({ label: PRODUCT_NAMES[v.vendor] ?? v.vendor, value: v.pct }))} max={Math.max(...vendors.map((v) => v.pct))} on={(i) => vendors[i].vendor === product} />
              {size !== "all" && <Note>Ramp doesn't split vendors by company size, so this shows all sizes.</Note>}
            </>
          ) : (
            <BarList rows={ramp.sizes.map((s) => ({ label: s.label.replace(" businesses", ""), value: s.pct }))} max={100} on={(i) => size === "all" || ramp.sizes[i].size === size} />
          )}
        </Panel>

        <Panel eyebrow="Talking about AI to investors" title="ARC AI Adoption Index"
          src={data.adoption ? <>Latest 10-K/10-Q · every quote checked · run {data.adoption.period}</> : "SEC filings"}>
          {!arc ? <Unavailable what="ARC AI Adoption Index" /> : arc.n === 0 ? (
            <p className="text-sm text-muted">{size === "mid" ? "Mid caps appear after their first index run." : "No companies in this group yet."}</p>
          ) : (
            <>
              <div className="num text-[24px] font-bold">{arc.pct}%</div>
              <div className="text-xs text-muted mb-1.5">of {SIZE_WORDS[size]} make a concrete AI claim ({arc.with_claim} of {arc.n})</div>
              <div className="flex h-3 overflow-hidden rounded-sm" aria-hidden>
                <i style={{ width: `${arc.depth[0]}%`, background: C.borderStrong }} />
                <i style={{ width: `${arc.depth[1]}%`, background: C.jobs }} />
                <i style={{ width: `${arc.depth[2]}%`, background: C.accent }} />
              </div>
              <div className="text-xs text-muted mt-1 mb-2.5">Of those: {arc.depth[0]}% piloting · {arc.depth[1]}% using it today · {arc.depth[2]}% earning revenue from it</div>
              <BarList rows={arc.sectors.map((s) => ({ label: `${s.sector}${s.thin ? " · thin" : ""}`, value: s.pct }))} max={100} on={() => true} />
              {product === "all" && arc.quotes.map((q) => (
                <blockquote key={q.ticker} className="mt-2.5 border-l-2 border-accent pl-2.5 font-serif text-[13px] leading-[19px] text-text-2">
                  "{q.quote}"
                  <footer className="mt-0.5 font-sans text-[11px] text-muted">{company(q.name, q.ticker)} · latest filing</footer>
                </blockquote>
              ))}
              {product !== "all" && data.adoption && (
                <Note>
                  Filings rarely name the AI tools a company buys: {data.adoption.product_claims.named} of the{" "}
                  {data.adoption.product_claims.total} claims on file name a product, mostly the company's own. This panel ignores the product filter.
                </Note>
              )}
            </>
          )}
        </Panel>

        <Panel eyebrow="Using AI, self-reported" title="Census Bureau business survey"
          src={census ? <>Business Trends and Outlook Survey · every two weeks{census.ref_end && ` · to ${census.ref_end}`}</> : "Census Bureau"}>
          {!census ? <Unavailable what="Census Bureau" /> : (
            <>
              <div className="num text-[24px] font-bold">{censusPct ?? "—"}</div>
              <div className="text-xs text-muted mb-2.5">
                of {size === "all" ? "US firms" : `firms with ${CENSUS_SIZE[size]} employees (the range across their size classes)`} used AI in the last two weeks
              </div>
              <BarList rows={census.by_class.map((c) => ({ label: `${c.label} staff`, value: c.pct }))} max={Math.max(...census.by_class.map((c) => c.pct)) * 1.1}
                on={(i) => size === "all" || census.by_class[i].bucket === size} />
              {product !== "all" && <Note>The Census survey doesn't ask which AI product, so this panel ignores the product filter.</Note>}
              <p className="text-[11px] text-muted mt-2"><SourceLink title="Census Bureau" url={census.source.url} /></p>
            </>
          )}
        </Panel>
      </div>
    </Chapter>
  );
}
