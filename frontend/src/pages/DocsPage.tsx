import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/cn";
import { isEnabled } from "@/models/registry";

// Long-form "how it works" for every model on /models. The cards keep a short version and
// link here via `/docs#<id>`. No live numbers on purpose, so this page can't go stale.

interface Doc {
  id: string;
  group: string;
  name: string;
  tag?: string;
  lead: string;
  facts: [string, string][];
  sections: [string, ReactNode][];
  read: ReactNode;
  limits: ReactNode[];
}

const C = ({ children }: { children: ReactNode }) => (
  <code className="font-mono text-[11.5px] bg-surface-2 px-1 py-px rounded">{children}</code>
);

const WALK_FORWARD = (
  <p>
    Walk-forward: the history is split into 5 time blocks, and the model trains on everything before a block and is scored
    on that block, so it never sees the future. We report accuracy and the Brier score (the mean squared error of the
    probability: 0 is perfect, 0.25 is a coin flip). The Update Agent refits daily and only promotes a new fit whose Brier
    score is no more than 0.02 worse than the current model's.
  </p>
);

const ALL_DOCS: Doc[] = [
  {
    id: "pulse",
    group: "Regime nowcasters",
    name: "Pulse",
    tag: "growth",
    lead: "Is US manufacturing in expansion next month? Pulse gives the probability, from five leading indicators.",
    facts: [["Type", "XGBoost classifier"], ["Output", "P(expansion), 0–100%"], ["Horizon", "1 month ahead"], ["Refit", "Daily, gated"]],
    sections: [
      ["What it predicts", <p>The target is the average of the Empire State and Philly Fed manufacturing diffusion indexes, a free stand-in for the ISM PMI (FRED stopped carrying the ISM series in 2024). A reading above 0 means more firms report growth than decline. The label is 1 when next month's reading is above 0.</p>],
      ["Inputs", <>
        <ul className="list-disc pl-5 space-y-1">
          <li>10-year Treasury yield (FRED <C>DGS10</C>)</li>
          <li>Initial jobless claims (<C>ICSA</C>)</li>
          <li>Philly Fed leading index (<C>USSLIND</C>; discontinued in 2020, so recent rows are blank)</li>
          <li>Cyclicals vs defensives, <C>XLY/XLP</C> (Yahoo Finance)</li>
          <li>Real disposable personal income (<C>DSPIC96</C>)</li>
          <li>The target's own recent values</li>
        </ul>
        <p className="mt-2">Each input enters as its current value plus 3 monthly lags.</p>
      </>],
      ["Method", <p>100 boosted trees of depth 1 (each tree is a single yes/no split, which keeps the model simple and hard to overfit), learning rate 0.1, trained on monthly data since 2000. The output is a probability; 50% or more is the "expansion" call.</p>],
      ["How it is tested", WALK_FORWARD],
    ],
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
    sections: [
      ["What it predicts", <p>The label is 1 when next month's CPI All Items (seasonally adjusted) month-over-month change is larger than this month's. An earlier version asked "will CPI go up?", but CPI rises in about 82% of months, so that question carried almost no signal.</p>],
      ["Inputs", <p>PPI, WTI and Brent crude, the Bloomberg Commodity Index, 5- and 10-year breakevens, the trade-weighted dollar, University of Michigan 1-year inflation expectations, rent CPI, average hourly earnings and Case-Shiller home prices. Each enters as 1-month and 12-month % changes, with 3 monthly lags.</p>],
      ["Method", <p>The same setup as Pulse: 100 depth-1 boosted trees, learning rate 0.1, monthly data since 2000.</p>],
      ["How it is tested", WALK_FORWARD],
    ],
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
    sections: [
      ["What it predicts", <p>For each month-end, the label is 1 if SPY's largest peak-to-trough drop over the following 30 days is worse than −5%.</p>],
      ["Inputs", <ul className="list-disc pl-5 space-y-1">
        <li>High-yield and investment-grade credit spreads (<C>BAMLH0A0HYM2</C>, <C>BAMLC0A0CM</C>)</li>
        <li>VIX (<C>VIXCLS</C>) and MOVE bond-market volatility (<C>^MOVE</C>)</li>
        <li>The broad trade-weighted dollar (<C>DTWEXBGS</C>)</li>
        <li>The HYG/IEF ratio, high-yield vs Treasury bond ETFs</li>
      </ul>],
      ["Method", <p>200 boosted trees of depth 4 with 80% row and feature sampling. Drawdowns are rare, so class weights scale up the drawdown months to keep the model from always answering "no".</p>],
    ],
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
    sections: [
      ["Technical score", <p>RSI-14, MACD histogram, price vs the 50- and 200-day averages, and 3-month return. Each metric is z-scored across all stocks, clipped at ±3σ, scaled to −1…+1 and averaged.</p>],
      ["Fundamental score", <p>Revenue growth, earnings growth and P/E relative to the sector median (cheaper scores higher), scored the same way. Prices and fundamentals come from Yahoo Finance.</p>],
      ["Divergence and labels", <p>Divergence = technical − fundamental per stock, then market-cap-weighted across the sector's top 10. At +0.30 or above a sector is labelled euphoric (price ahead of fundamentals); at −0.30 or below, fearful (fundamentals nobody is buying); otherwise fair.</p>],
      ["Stock-specific or sector-wide", <p>Code, not the LLM, decides the verdict. If one stock supplies at least 50% of the divergence it is stock-specific. If at least 7 of the 10 stocks share its sign it is sector-wide. Otherwise it is mixed.</p>],
      ["Explainer", <p>Two LLM agents write the summary and per-sector prose from the numbers. They describe and never recommend; if they fail, the page shows the numbers alone.</p>],
    ],
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
    sections: [
      ["Talk", <p>An LLM reads AI passages in the latest 10-K or 10-Q and rates each claim 1 (pilot), 2 (deployed) or 3 (revenue-linked). Every quote must appear word for word in the filing or it is dropped. The score is depth-weighted claims per 1,000 words. A filing is only ever sent to the LLM once.</p>],
      ["Hire", <>
        <p>The share of open job postings that are AI/ML roles. Code, not an LLM, decides which titles count. Postings are read three ways:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li><b>Platform readers</b> for Greenhouse, Lever, Workday, Oracle, UKG and Amazon, up to 2,000 postings per company.</li>
          <li><b>Saved recipes</b> for companies with their own careers site: a small file saying where the titles are, replayed by code every run.</li>
          <li><b>The Recipe Writer</b>, an LLM agent that explores a careers site once to write that recipe. It is kept only if it finds at least 90% of the jobs the site shows.</li>
        </ul>
        <p className="mt-2">The reading is averaged over the last 7 bi-weekly snapshots.</p>
      </>],
      ["Spend", <p>Capex plus R&amp;D as a share of revenue, trailing twelve months, from Yahoo Finance.</p>],
      ["Score and roll-up", <p>Each pillar is z-scored across all companies, clipped at ±3σ and mapped to 0–100 (average 50). A company needs at least 2 of the 3 pillars. Scores roll up equal-weighted (the headline) and market-cap-weighted per sector and size bucket; a cell with fewer than 5 companies is flagged thin.</p>],
    ],
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
    lead: "What moved equities, Treasuries and gold this week, month and quarter? Each driver's share of the move, with data releases counted only as their surprise.",
    facts: [["Type", "Ridge attribution"], ["Output", "% pts per driver"], ["Assets", "S&P 500, IEF, GLD"], ["Refresh", "Weekly (Friday close)"]],
    sections: [
      ["Drivers", <p>Weekly moves in the 2-year yield, the 10-year real yield and breakeven, the term premium, the high-yield spread, NFCI and the Fed balance sheet (FRED), VIX (Yahoo), the broad dollar, and speculators' net futures positioning in each asset (CFTC). Each asset only uses the drivers that plausibly matter for it: the dollar isn't used for Treasuries and the breakeven isn't used for equities.</p>],
      ["Surprises, not data", <p>Markets price the consensus before a release, so CPI, PCE, payrolls, ISM and GDP enter as actual minus consensus, divided by that release's typical surprise. Both numbers come from a cited web search and are kept only if both appear in the cited source; otherwise that release counts as no surprise and is listed as a data gap.</p>],
      ["Fit", <p>For each asset, a ridge regression of weekly returns on the drivers over the last 104 weeks. Ridge shrinks sensitivities when drivers overlap; its strength is picked automatically.</p>],
      ["Contributions", <p>A driver's contribution is its sensitivity times how much it moved over the window. Whatever the drivers don't explain is shown as Unexplained, so the bars always add up to the actual move.</p>],
      ["Groups", <p>Drivers that move together (the rate measures; VIX and credit spreads; the two liquidity measures) are shown as one bar. The model gets their joint effect right but can't reliably split it, so the split inside a group is marked uncertain.</p>],
    ],
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

function Article({ d }: { d: Doc }) {
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
        {d.sections.map(([title, body]) => (
          <section key={title}>
            <h4 className="mt-5 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent">{title}</h4>
            {body}
          </section>
        ))}
        <h4 className="mt-5 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent">How to read it</h4>
        <div className="rounded-r-lg border-l-[3px] border-accent bg-surface-2 px-3.5 py-2.5">{d.read}</div>
        <h4 className="mt-5 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent">Limitations</h4>
        <ul className="rounded-lg bg-warning-soft px-3.5 py-2.5 pl-8 list-disc space-y-1 text-[#7c4a03]">
          {d.limits.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </div>
      <Link to="/models" className="mt-4 inline-block text-xs font-medium text-accent hover:underline">See the live card on Models →</Link>
    </article>
  );
}

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
      <h2 className="text-base font-semibold text-text">Documentation</h2>
      <p className="text-xs text-muted mt-0.5">
        How each model on the Models page works: what it predicts, what it reads, how it is tested, and where it falls short.
      </p>

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
