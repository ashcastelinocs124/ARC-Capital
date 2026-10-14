import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { PageIntro } from "@/components/layout/PageIntro";

// /about: what ARC Research is and who's behind it. Static copy, so the public snapshot needs nothing new.
const LINKS: [string, string][] = [
  ["Newsletter", "https://archresearch.substack.com/"],
  ["X · @AshleynCas46131", "https://x.com/AshleynCas46131"],
  ["LinkedIn", "https://www.linkedin.com/in/ashleyn-castelino/"],
  ["YouTube", "https://www.youtube.com/@ashleyn4869"],
];

const HOW: [string, string][] = [
  ["Data first.", "Releases, prices and prediction markets come from FRED, BLS, Yahoo Finance and Polymarket; news comes from cited web search."],
  ["Agents do the legwork.", "Analyst agents gather the day's facts; an editor agent writes the note."],
  ["Code checks the numbers.", "Every figure in a note must match a fact behind it, or the note doesn't ship."],
  ["Open methods.", "The models and agents are explained under How it works."],
];

const PUBS: [string, string, string, string][] = [
  ["/updates", "Every weekday", "Memo", "The daily note: what moved, and why it matters."],
  ["/deep-research", "Sundays", "Deep Research", "The week's 10 to 12 trends, researched in depth."],
  ["/models", "Always on", "Models", "Growth and inflation nowcasts, sector sentiment, AI adoption, cross-asset drivers."],
];

export default function AboutPage() {
  return (
    <div className="space-y-5 p-4 md:p-8">
      <PageIntro kicker="About" title="Independent macro and AI research">
        ARC Research follows the forces moving markets: growth, rates and inflation, and the AI build-out, from frontier
        models to chips and the semiconductor supply chain. It publishes every weekday, written by one independent
        researcher with a desk of self-built AI agents, and every number is checked against its source before it goes out.
      </PageIntro>

      <div className="grid gap-5 lg:grid-cols-[1.25fr_1fr]">
        <section className="card p-6">
          <div className="flex items-center gap-4">
            <img src="/team/ashleyn.png" alt="Ashleyn Castelino" width={84} height={84}
              className="h-[84px] w-[84px] shrink-0 rounded-full border-2 border-accent/50 object-cover object-[40%_30%]" />
            <div>
              <h2 className="font-serif text-[22px] font-semibold leading-tight text-text">Ashleyn Castelino</h2>
              <p className="mt-0.5 text-[13px] text-muted">Analyst · macro &amp; AI research · agents &amp; ML systems</p>
            </div>
          </div>
          <div className="mt-5 space-y-3 text-[14.5px] leading-relaxed text-text-2">
            <p>
              I'm Ashleyn Castelino, and I do independent research on macroeconomics and AI, from rates, inflation and
              growth to AI models, chips and semiconductors. I started ARC to make that research daily, open and
              checkable: the data comes straight from the source, the reasoning is written out, and the methods are
              documented on this site.
            </p>
            <p>
              I also build the systems behind it: the AI agents that gather the day's data and write the Morning Note and
              the Sunday deep dive, and the machine-learning models on this site: growth and inflation nowcasters,
              sector sentiment, an AI adoption index and cross-asset drivers.
            </p>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {LINKS.map(([label, href]) => (
              <a key={href} href={href} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1.5 text-[13px] text-text hover:border-accent hover:text-accent">
                {label} <ArrowUpRight className="h-3.5 w-3.5" />
              </a>
            ))}
          </div>
        </section>

        <section className="card p-6">
          <h2 className="mb-3 font-serif text-xl font-semibold text-text">How ARC works</h2>
          <ul className="list-disc space-y-1.5 pl-5 text-[14px] leading-relaxed text-text-2">
            {HOW.map(([lead, rest]) => (
              <li key={lead}><b className="text-text">{lead}</b> {rest}</li>
            ))}
          </ul>
        </section>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {PUBS.map(([to, when, name, blurb]) => (
          <Link key={to} to={to} className="card block p-5 transition-colors hover:border-accent">
            <div className="text-[11px] font-bold uppercase tracking-[0.08em] text-accent">{when}</div>
            <div className="mt-1 font-semibold text-text">{name}</div>
            <p className="mt-1 text-[13px] leading-snug text-muted">{blurb}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
