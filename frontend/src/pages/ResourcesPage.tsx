import { ArrowUpRight } from "lucide-react";
import { PageIntro } from "@/components/layout/PageIntro";
import { C } from "@/lib/theme";

// Hand-kept: add a deck as one line in its group, newest first. A deck with a PDF in the public
// Workshop-Slides repo links there; the rest link to the claude.ai deck, which must be shared publicly.
const GH = "https://github.com/ashcastelinocs124/Workshop-Slides/blob/main/";
const ART = "https://claude.ai/artifact/";

const BOOK = {
  url: "https://ashcastelinocs124.github.io/Macro-Investing-Textbook/",
  source: "https://github.com/ashcastelinocs124/Macro-Investing-Textbook",
  parts: ["How the economy works", "Policy makers", "The asset classes", "The global system", "Doing macro"],
};

type Deck = { title: string; date: string; slides: number; blurb: string; url: string };
const GROUPS: { name: string; sub: string; color: string; decks: Deck[] }[] = [
  { name: "AI industry", sub: "who builds, funds and powers frontier AI", color: C.ai, decks: [
    { title: "Learning on the job: continual learning for LLMs", date: "Oct 8, 2026", slides: 50, url: `${GH}AI/ai-update/Continual%20Learning%20Labs%20%26%20Neolabs.pdf`,
      blurb: "How LLMs could keep learning after deployment, the labs betting on it, and what it means for chips." },
    { title: "Neoclouds & Neolabs", date: "Oct 6, 2026", slides: 63, url: `${GH}Finance/market-update/Neoclouds%20%26%20Neolabs.pdf`,
      blurb: "How GPU-rental neoclouds and well-funded new AI labs work, how they are financed, and what could break." },
    { title: "AI Data Centers Are Going to Space", date: "Sep 24, 2026", slides: 22, url: `${ART}YXCeVqA5xvibrikHoh2QnS`,
      blurb: "Google's Project Suncatcher, and the five engineering problems between a design paper and an orbital AI cluster." },
    { title: "Money for Machines", date: "Sep 23, 2026", slides: 31, url: `${GH}Finance/market-update/Money%20for%20Machines.pdf`,
      blurb: "Crypto payment rails for AI agents are built and backed by incumbents; real agent demand is still tiny." },
  ] },
  { name: "Macro", sub: "elections, policy and where capital goes", color: C.inflation, decks: [
    { title: "Brazil 2026: the runoff, the market, the Congress", date: "Oct 8, 2026", slides: 57, url: `${ART}2wP4yaiqmaUD12W3CAAqj4`,
      blurb: "Brazil's Lula vs Flávio Bolsonaro runoff, how markets reacted, the new Congress and the macro backdrop." },
    { title: "Where Money Goes Next", date: "Sep 28, 2026", slides: 23, url: `${ART}PVSvGEmGpQGUi1Ev7WrG7p`,
      blurb: "How AI, energy, government debt, metals and crypto connect, and where capital may be positioned next." },
  ] },
  { name: "Weekly market updates", sub: "the week in markets, presented live", color: C.jobs, decks: [
    { title: "Tech blinks, the Dow holds", date: "Week of Oct 12–16, 2026", slides: 38, url: `${ART}87dygTfrUjE1hXWZUbgyjU`,
      blurb: "Money left AI hardware and AI credit for defensives and energy, as CoreWeave fell and oil topped $100." },
    { title: "Weekly Market Update", date: "Week ending Sep 18, 2026", slides: 28,
      url: `${GH}Finance/market-update/Weekly%20Market%20Update%20%E2%80%94%20Sept%2018%2C%202026.pdf`,
      blurb: "The Fed hiked, the 10-year hit 5% and breadth cracked; plus Japan, AI and the Anthropic IPO." },
  ] },
];

const out = { target: "_blank", rel: "noopener noreferrer" } as const;

export default function ResourcesPage() {
  const count = GROUPS.reduce((n, g) => n + g.decks.length, 0);
  return (
    <div className="space-y-5 p-4 md:p-8">
      <PageIntro kicker="Resources" title="Talks, slides and the Global Macro Cookbook">
        The slides from talks I've given on AI and global macro, plus a free textbook I wrote. Each card opens the slides;
        the book opens on its own site.
      </PageIntro>

      <section className="card grid overflow-hidden md:grid-cols-[1.15fr_1fr]">
        <div className="border-b border-border p-5 md:border-b-0 md:border-r md:p-7">
          <div className="eyebrow">Book · free · interactive</div>
          <h2 className="mb-2 mt-2 font-serif text-[25px] font-bold leading-tight text-text md:text-[30px]">Global Macro Cookbook</h2>
          <p className="max-w-[460px] text-[14.5px] leading-[22px] text-text-2">
            A free, interactive textbook on how the global economy moves markets: from the business cycle and central banks to
            every major asset class.
          </p>
          <div className="mt-5 flex flex-wrap gap-2.5">
            <a href={BOOK.url} {...out} className="inline-flex items-center gap-1 rounded-full bg-accent px-[18px] py-2 text-[13.5px] font-semibold text-on-accent hover:bg-accent-hover">
              Read the book <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
            <a href={BOOK.source} {...out} className="inline-flex items-center gap-1 rounded-full border border-border-strong px-[18px] py-2 text-[13.5px] font-semibold text-text hover:border-text">
              Source on GitHub <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
        <div className="bg-surface-3/45 px-5 py-4 md:px-7 md:py-6">
          <div className="eyebrow">Five parts</div>
          <ol className="mt-2.5">
            {BOOK.parts.map((p, i) => (
              <li key={p} className="grid grid-cols-[34px_1fr] items-baseline border-b border-dashed border-border py-2 text-sm text-text last:border-b-0">
                <b className="font-serif text-accent">{["I", "II", "III", "IV", "V"][i]}</b>{p}
              </li>
            ))}
          </ol>
        </div>
      </section>

      <div className="flex flex-wrap items-baseline justify-between gap-3 pt-2">
        <h2 className="text-xl font-semibold tracking-tight text-text">
          Slides <span className="ml-1 text-xs font-normal text-muted">{count} talks</span>
        </h2>
        <a href="https://github.com/ashcastelinocs124/Workshop-Slides" {...out} className="text-[13px] font-semibold text-accent hover:text-accent-hover">
          All workshop slides on GitHub ↗
        </a>
      </div>
      {GROUPS.map((g) => (
        <section key={g.name}>
          <h3 className="mb-2.5 flex items-center gap-2 text-[13px] font-semibold text-text-2">
            <span className="h-2 w-2 rounded-full" style={{ background: g.color }} />
            {g.name} <span className="font-normal text-muted">· {g.sub}</span>
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 md:gap-4">
            {g.decks.map((d) => (
              <a key={d.url} href={d.url} {...out} className="card flex flex-col p-[18px] transition-shadow hover:shadow-card-hover">
                <div className="flex items-center justify-between gap-2">
                  <span className="eyebrow">{d.date}</span>
                  <span className="pill">{d.slides} SLIDES</span>
                </div>
                <h4 className="mt-3 text-[15.5px] font-semibold leading-snug text-text">{d.title}</h4>
                <p className="mt-1.5 flex-1 text-[12.5px] leading-relaxed text-muted">{d.blurb}</p>
                <div className="mt-3.5 text-[13px] font-semibold text-accent">View slides ↗</div>
              </a>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
