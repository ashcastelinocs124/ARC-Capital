import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Download, X } from "lucide-react";
import { PageIntro } from "@/components/layout/PageIntro";
import { C } from "@/lib/theme";

// Hand-kept: add a deck as one line in its group, newest first. Every deck is a PDF (`pdf`) that opens in a
// viewer on this page and downloads: one in the public Workshop-Slides repo comes through jsDelivr (GitHub's
// raw links refuse framing), and a claude.ai deck is exported (Download → PDF) into public/slides/, since
// claude.ai can't be framed. ponytail: jsDelivr allows 20 MB a file and caches @main up to 12 h, so a
// replaced PDF can lag; purge at purge.jsdelivr.net or move it to public/slides/ if either bites.
const CDN = "https://cdn.jsdelivr.net/gh/ashcastelinocs124/Workshop-Slides@main/";
const SITE = "/slides/";

const BOOK = {
  url: "https://ashcastelinocs124.github.io/Macro-Investing-Textbook/",
  source: "https://github.com/ashcastelinocs124/Macro-Investing-Textbook",
  parts: ["How the economy works", "Policy makers", "The asset classes", "The global system", "Doing macro"],
};

type Deck = { title: string; date: string; slides: number; blurb: string; pdf: string; video?: string }; // video: the talk's Substack post
const GROUPS: { name: string; sub: string; color: string; decks: Deck[] }[] = [
  { name: "AI models", sub: "the labs, the models and how AI gets used and paid for", color: C.ai, decks: [
    { title: "Anthropic's S-1: the IPO teardown", date: "Nov 9, 2026", slides: 56, pdf: `${SITE}anthropic-s1-ipo-teardown.pdf`,
      blurb: "Anthropic's IPO filing: $33.2B of revenue in nine months, a $104B loss that is mostly accounting, an $895B compute bill and founder control." },
    { title: "AI models & semis update", date: "Nov 7, 2026", slides: 46, pdf: `${SITE}ai-models-semis-2026-11-07.pdf`,
      blurb: "How Thinking Machines and Cognition trained their new models, METR on AI R&D speed, TSMC's 3D DRAM and DeepSeek on Ascend." },
    { title: "Learning on the job: continual learning for LLMs", date: "Oct 8, 2026", slides: 50, pdf: `${CDN}AI/ai-update/Continual%20Learning%20Labs%20%26%20Neolabs.pdf`,
      blurb: "How LLMs could keep learning after deployment, the labs betting on it, and what it means for chips." },
    { title: "Neoclouds & Neolabs", date: "Oct 6, 2026", slides: 63, pdf: `${CDN}Finance/market-update/Neoclouds%20%26%20Neolabs.pdf`,
      blurb: "How GPU-rental neoclouds and well-funded new AI labs work, how they are financed, and what could break." },
    { title: "Money for Machines", date: "Sep 23, 2026", slides: 31, pdf: `${CDN}Finance/market-update/Money%20for%20Machines.pdf`,
      blurb: "Crypto payment rails for AI agents are built and backed by incumbents; real agent demand is still tiny." },
  ] },
  { name: "Semis & chips", sub: "the GPUs, data centers and cooling that AI runs on", color: C.earnings, decks: [
    { title: "Cooling the AI GPU", date: "Oct 26, 2026", slides: 37, pdf: `${SITE}cooling-ai-gpu.pdf`,
      blurb: "Single-phase vs two-phase liquid cooling: why AI racks need it, OCP's specs, the fluid risk and who profits." },
    { title: "AI Data Centers Are Going to Space", date: "Sep 24, 2026", slides: 22, pdf: `${SITE}ai-data-centers-space.pdf`,
      blurb: "Google's Project Suncatcher, and the five engineering problems between a design paper and an orbital AI cluster." },
  ] },
  { name: "Macro", sub: "elections, policy and where capital goes", color: C.inflation, decks: [
    { title: "Data Centers on the Ballot", date: "Nov 5, 2026", slides: 28, pdf: `${SITE}data-centers-on-the-ballot.pdf`,
      video: "https://archresearch.substack.com/p/data-center-buildout-not-to-be-worried",
      blurb: "A 50-state rules index, $450B of announced projects, what the 2026 winners said, and voters turning against them." },
    { title: "Brazil 2026: the runoff, the market, the Congress", date: "Oct 8, 2026", slides: 57, pdf: `${SITE}brazil-2026.pdf`,
      blurb: "Brazil's Lula vs Flávio Bolsonaro runoff, how markets reacted, the new Congress and the macro backdrop." },
    { title: "Where Money Goes Next", date: "Sep 28, 2026", slides: 23, pdf: `${SITE}where-money-goes-next.pdf`,
      blurb: "How AI, energy, government debt, metals and crypto connect, and where capital may be positioned next." },
  ] },
  { name: "Weekly market updates", sub: "the week in markets, presented live", color: C.jobs, decks: [
    { title: "Weekly Market Update #4 | The AI unwind", date: "Week of Nov 2–6, 2026", slides: 55, pdf: `${SITE}weekly-market-update-2026-11-06.pdf`,
      blurb: "An election rally, then the Nov 5 AI crash: chips fell 12.1% on the week; the rotation, the fundamentals and Asia.",
      video: "https://archresearch.substack.com/p/weekly-market-update" },
    { title: "Weekly Market Update #3 | Rotation week: tech sinks, small caps hold", date: "Week of Oct 26–30, 2026", slides: 40, pdf: `${SITE}weekly-market-update-2026-10-30.pdf`,
      blurb: "Money left megacap tech for small caps as Alphabet and Intel sank, the Fed held 10–2 and Anthropic filed its S-1." },
    { title: "Weekly Market Update #2 | Tech blinks, the Dow holds", date: "Week of Oct 12–16, 2026", slides: 38, pdf: `${SITE}weekly-market-update-2026-10-16.pdf`,
      blurb: "Money left AI hardware and AI credit for defensives and energy, as CoreWeave fell and oil topped $100." },
    { title: "Weekly Market Update #1", date: "Week ending Sep 18, 2026", slides: 28,
      pdf: `${CDN}Finance/market-update/Weekly%20Market%20Update%20%E2%80%94%20Sept%2018%2C%202026.pdf`,
      blurb: "The Fed hiked, the 10-year hit 5% and breadth cracked; plus Japan, AI and the Anthropic IPO." },
  ] },
];

const out = { target: "_blank", rel: "noopener noreferrer" } as const;
const BTN = "inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-semibold";
const PRIMARY = `${BTN} bg-accent text-on-accent hover:bg-accent-hover`;
const SECONDARY = `${BTN} border border-border-strong text-text hover:border-text`;

// A cross-origin <a download> is ignored (the browser just opens the PDF), so fetch it and save it under its title.
async function download(d: Deck) {
  const href = d.pdf;
  try {
    const r = await fetch(href);
    if (!r.ok) throw new Error(String(r.status));
    const url = URL.createObjectURL(await r.blob());
    Object.assign(document.createElement("a"), { href: url, download: `${d.title.replace(/[\\/:*?"<>|]/g, "")}.pdf` }).click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  } catch {
    window.open(href, "_blank", "noopener");
  }
}

function DownloadButton({ deck, className, label }: { deck: Deck; className: string; label: string }) {
  const [busy, setBusy] = useState(false);
  const click = () => {
    setBusy(true);
    download(deck).finally(() => setBusy(false));
  };
  return (
    <button className={className} disabled={busy} onClick={click}>
      {busy ? "Downloading…" : label} <Download className="h-3.5 w-3.5" />
    </button>
  );
}

// The pop-up viewer: a native <dialog> (Esc closes it, focus stays inside), the PDF in the browser's own viewer.
function Viewer({ deck, onClose }: { deck: Deck | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (deck) ref.current?.showModal();
    else ref.current?.close();
  }, [deck]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && ref.current.close()} // a click on the backdrop
      className="m-auto h-[min(92vh,920px)] max-h-none w-[min(94vw,1320px)] max-w-none overflow-hidden rounded-xl border border-border-strong bg-surface p-0 text-text backdrop:bg-black/70"
    >
      {deck && (
        <div className="flex h-full flex-col">
          <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="truncate text-[15px] font-semibold">{deck.title}</div>
              <div className="text-xs text-muted">
                {deck.date} · {deck.slides} slides
              </div>
            </div>
            <DownloadButton deck={deck} className={PRIMARY} label="Download PDF" />
            <a href={deck.pdf} {...out} className={SECONDARY}>
              Open in new tab <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
            <button onClick={() => ref.current?.close()} aria-label="Close" className="rounded-full p-1.5 text-text-2 hover:text-text">
              <X className="h-5 w-5" />
            </button>
          </div>
          <iframe src={deck.pdf} title={deck.title} className="w-full flex-1 border-0 bg-surface-3" />
        </div>
      )}
    </dialog>
  );
}

export default function ResourcesPage() {
  const count = GROUPS.reduce((n, g) => n + g.decks.length, 0);
  const [open, setOpen] = useState<Deck | null>(null);
  // phones get the PDF in a new tab: mobile browsers show one page of a framed PDF, or none
  const view = (d: Deck) => {
    if (window.matchMedia("(max-width: 767px)").matches) window.open(d.pdf, "_blank", "noopener");
    else setOpen(d);
  };
  return (
    <div className="space-y-5 p-4 md:p-8">
      <PageIntro kicker="Resources" title="Talks, slides and the Global Macro Cookbook">
        The slides from talks I've given on AI and global macro, plus a free textbook I wrote. View a deck right here or
        download its PDF; the book opens on its own site.
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
          All presentations on GitHub ↗
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
              <div key={d.title} className="card flex flex-col p-[18px]">
                <div className="flex items-center justify-between gap-2">
                  <span className="eyebrow">{d.date}</span>
                  <span className="pill">{d.slides} SLIDES</span>
                </div>
                <h4 className="mt-3 text-[15.5px] font-semibold leading-snug text-text">{d.title}</h4>
                <p className="mt-1.5 flex-1 text-[12.5px] leading-relaxed text-muted">{d.blurb}</p>
                <div className="mt-3.5 flex flex-wrap gap-2">
                  <button onClick={() => view(d)} className={PRIMARY}>
                    View
                  </button>
                  <DownloadButton deck={d} className={SECONDARY} label="Download" />
                  {d.video && (
                    <a href={d.video} {...out} className={SECONDARY} aria-label={`Watch the talk: ${d.title} (opens Substack)`}>
                      Watch <ArrowUpRight className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
      <Viewer deck={open} onClose={() => setOpen(null)} />
    </div>
  );
}
