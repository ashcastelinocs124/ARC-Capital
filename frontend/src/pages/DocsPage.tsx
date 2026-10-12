import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/cn";
import { isEnabled } from "@/models/registry";
import { PageIntro } from "@/components/layout/PageIntro";

// High-level guide for every model on /models (cards link here via `/docs#<id>`). No live numbers on
// purpose, so this page can't go stale. The detailed method, inputs and testing live in
// admin/private/docsDetail.tsx, which ships as its own file behind the admin password (see middleware.ts).

interface Doc {
  id: string;
  group: string;
  name: string;
  tag?: string;
  lead: string;
  facts: [string, string][];
  overview: string; // the public what-it-predicts; the method, inputs and testing are admin-only (admin/private/docsDetail.tsx)
  read: ReactNode;
  limits: ReactNode[];
}

const ALL_DOCS: Doc[] = [
  {
    id: "pulse",
    group: "Regime nowcasters",
    name: "Pulse",
    tag: "growth",
    lead: "Is US manufacturing in expansion next month? Pulse gives the probability, from five leading indicators.",
    facts: [["Type", "XGBoost classifier"], ["Output", "P(expansion), 0–100%"], ["Horizon", "1 month ahead"], ["Refit", "Daily, gated"]],
    overview: "The chance that US manufacturing activity is above its neutral level next month, estimated from a handful of leading economic indicators.",
    read: <>A reading of 80% means the model puts an 80% chance on the composite being above 0 next month. Compare its accuracy with how often expansion happens anyway: a model is only useful if it beats that base rate.</>,
    limits: [
      "The target is a proxy for the ISM, built from two regional surveys.",
      "One input, the Philly Fed leading index, stopped updating in 2020.",
      'Monthly data arrives with a lag; "Data through" on the card shows the latest month used.',
    ],
  },
  {
    id: "pressure",
    group: "Regime nowcasters",
    name: "Pressure",
    tag: "inflation",
    lead: "Will CPI inflation speed up next month? Pressure gives the probability that next month's CPI change is larger than this month's.",
    facts: [["Type", "XGBoost classifier"], ["Output", "P(CPI accelerates)"], ["Horizon", "1 month ahead"], ["Refit", "Daily, gated"]],
    overview: "Whether CPI inflation speeds up next month. The question is about the direction of change, not whether prices rise.",
    read: <>Above 50% means the model expects inflation to speed up next month; below 50%, to hold steady or slow down. It says nothing about the level of inflation, only its direction of change.</>,
    limits: [
      "Accelerating vs decelerating is a noisy call; expect lower accuracy than Pulse.",
      "A source with no recent data is skipped in that fit; the card shows it faded.",
    ],
  },
  {
    id: "risk-off",
    group: "Market risk",
    name: "Risk-off classifier",
    lead: "Will the S&P 500 fall more than 5% peak-to-trough in the 30 days after month-end?",
    facts: [["Type", "XGBoost classifier"], ["Output", "P(risk-off drawdown)"], ["Horizon", "30 days"], ["Training", "Monthly since 2000"]],
    overview: "The chance of a sharp S&P 500 drawdown, worse than 5% peak-to-trough, in the 30 days after month-end.",
    read: <>The output is a probability, not a call. Compare it with the base rate of 5% drawdowns: a reading well above that base rate is the signal.</>,
    limits: [
      'Shows "Not trained" until a model has been saved.',
      "Rare events make for few positive examples, so the estimate is noisy.",
    ],
  },
  {
    id: "sector-sentiment",
    group: "Signals",
    name: "Sector Sentiment",
    lead: "Where has price run ahead of the business, or fallen behind it? Technical score minus fundamental score, for each GICS sector's 10 largest stocks.",
    facts: [["Type", "Rules-based score"], ["Output", "Divergence, −1 to +1"], ["Universe", "11 sectors × top 10"], ["Refresh", "Refresh button"]],
    overview: "How strongly each sector's stocks are trending (technical) against how well the underlying businesses are doing (fundamental). A large gap means price has run ahead of, or fallen behind, the business.",
    read: <>A euphoric tech sector flagged stock-specific usually means one mega-cap is carrying the reading. Check the stock table before reading it as a sector call.</>,
    limits: [
      "Only the 10 largest stocks per sector are scored.",
      "Yahoo Finance fundamentals have gaps; a stock with none is scored on technicals only and flagged.",
    ],
  },
  {
    id: "adoption",
    group: "Signals",
    name: "AI Adoption Index",
    lead: "How far has each company actually adopted AI? Three pillars, Talk, Hire and Spend, rolled up by sector and size.",
    facts: [["Type", "Research index"], ["Output", "0–100, average 50"], ["Universe", "Large + small caps"], ["Refresh", "Bi-weekly"]],
    overview: "One score per company built from what it says about AI (Talk), who it hires (Hire) and how much it invests (Spend), rolled up by sector and size.",
    read: <>A score of 50 is average for this universe, not "half adopted". Compare cells within the same size bucket; large caps spend and hire on a different scale.</>,
    limits: [
      "Not every company has a readable job board, so some are scored on Talk and Spend only.",
      "Spend counts all capex and R&D, not just AI.",
      "Talk measures what companies say, which can run ahead of what they do.",
    ],
  },
  {
    id: "cross-asset",
    group: "Signals",
    name: "Cross-Asset Drivers",
    lead: "What moved equities and Treasuries this week, month and quarter? Each driver's share of the move, with data releases counted only as their surprise.",
    facts: [["Type", "Ridge attribution"], ["Output", "% pts per driver"], ["Assets", "S&P 500, IEF"], ["Refresh", "Weekly (Friday close)"]],
    overview: "A split of what moved equities and Treasuries over the week, month and quarter into drivers, with an Unexplained remainder. It explains the past; it does not forecast.",
    read: <>A big Unexplained bar means the move came from something the drivers don't capture: earnings, geopolitics or noise. Check the out-of-sample figure: it says how much of a typical week the drivers explain for that asset.</>,
    limits: [
      "It explains past moves; it does not forecast.",
      "104 weeks holds only about 24 releases per series, so surprise sensitivities are noisy.",
      "Consensus figures come from web search and can be missing; misses count as no surprise.",
      "CFTC positions are as of Tuesday, released Friday.",
    ],
  },
];

// only models switched on in models/registry.ts
const DOCS = ALL_DOCS.filter((d) => isEnabled(d.id));

const GROUPS = [...new Set(DOCS.map((d) => d.group))];

export type DocDetail = [string, ReactNode][];

// detail = the admin-only method/inputs/testing sections; the public page passes none.
export function Article({ d, detail }: { d: Doc; detail?: DocDetail }) {
  return (
    <article id={d.id} className="scroll-mt-4 rounded-xl border border-border bg-surface px-5 py-5 md:px-6">
      <h3 className="text-lg font-semibold text-text flex items-center gap-2">
        {d.name}
        {d.tag && <span className="text-[10.5px] font-semibold px-2 py-px rounded-full bg-accent-soft text-accent">{d.tag}</span>}
      </h3>
      <p className="mt-1.5 text-base text-text-2">{d.lead}</p>
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-px bg-border border border-border rounded-lg overflow-hidden">
        {d.facts.map(([k, v]) => (
          <div key={k} className="bg-surface px-3 py-2 text-xs text-muted">
            {k}
            <div className="text-[12.5px] font-semibold text-text">{v}</div>
          </div>
        ))}
      </div>
      <div className="text-sm text-text-2 [&_p]:mb-2">
        <section>
          <h4 className="mt-5 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent">What it predicts</h4>
          <p>{d.overview}</p>
        </section>
        {detail?.map(([title, body]) => (
          <section key={title}>
            <h4 className="mt-5 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent">{title}</h4>
            {body}
          </section>
        ))}
        <h4 className="mt-5 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent">How to read it</h4>
        <div className="rounded-r-lg border-l-[3px] border-accent bg-surface-2 px-3.5 py-2.5">{d.read}</div>
        <h4 className="mt-5 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent">Limitations</h4>
        <ul className="rounded-lg bg-warning-soft px-3.5 py-2.5 pl-8 list-disc space-y-1 text-text-2">
          {d.limits.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </div>
      <Link to="/models" className="mt-4 inline-block text-xs font-medium text-accent hover:underline">See the live card on Models →</Link>
    </article>
  );
}

export const DOCS_LIST = DOCS;

export default function DocsPage() {
  const { hash } = useLocation();
  const [active, setActive] = useState(DOCS[0].id);

  // react-router doesn't scroll to #anchors on its own
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [hash]);

  // highlight the article nearest the top of the viewport
  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setActive(e.target.id)),
      { rootMargin: "0px 0px -70% 0px" },
    );
    DOCS.forEach((d) => { const el = document.getElementById(d.id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, []);

  return (
    <div className="p-4 md:p-8">
      <PageIntro kicker="Documentation" title="What every model tells you, and where it falls short"
        steps={["What it predicts", "How to read it", "Limitations"]}
        when={{ label: `${DOCS.length} models`, value: "documented" }}>
        A plain-English guide to each model on the Models page: what it predicts, how to read its output, and its
        known limitations.
      </PageIntro>

      {/* phones: contents as a row of chips */}
      <div className="md:hidden mt-4 flex flex-wrap gap-2">
        {DOCS.map((d) => (
          <a key={d.id} href={`#${d.id}`} className="text-xs px-2.5 py-1 rounded-full border border-border text-text-2">{d.name}</a>
        ))}
      </div>

      <div className="mt-5 grid md:grid-cols-[190px_1fr] gap-8 items-start">
        <nav className="hidden md:block sticky top-4">
          {GROUPS.map((g) => (
            <div key={g}>
              <div className="mt-3 mb-1 ml-2.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-2">{g}</div>
              {DOCS.filter((d) => d.group === g).map((d) => (
                <a key={d.id} href={`#${d.id}`}
                  className={cn("block px-2.5 py-1 border-l-2 text-[12.5px]",
                    active === d.id ? "border-accent text-accent font-semibold bg-surface-2" : "border-border text-muted hover:text-text")}>
                  {d.name}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <div className="space-y-5">
          {DOCS.map((d) => <Article key={d.id} d={d} />)}
        </div>
      </div>
    </div>
  );
}
