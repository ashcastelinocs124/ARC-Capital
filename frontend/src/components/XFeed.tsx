import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { X_PROFILE, type XPost } from "@/api/endpoints";
import { useXFeed } from "@/hooks/useXFeed";
import { cn } from "@/lib/cn";

// Your posts on X: Home's "Latest on X" row (XCard) and About's "On X" feed (XFeedCard).
// Every link is built by x_feed.py and checked by fetchXFeed: x.com/AshleynCas46131/status/<id>.

const TIME = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });
const DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const when = (at: string) => {
  const d = new Date(at); // the reader's own time zone, as on X
  return Number.isNaN(d.getTime()) ? "" : `${TIME.format(d)} · ${DAY.format(d)}`;
};
// The automated posts open with their series; anything else (typed by hand) has no tag.
const TAGS: [RegExp, string][] = [[/^MACRO · /, "Macro"], [/^AI · /, "AI"], [/^Before the open:/, "Theme Charts"], [/^(WEEK AHEAD|TODAY) · /, "Calendar"]];
const tagOf = (text: string) => TAGS.find(([re]) => re.test(text))?.[1];
const small = (img: string) => `${img}?name=small`; // X's CDN: 680 px wide

function XLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cn("fill-current", className)}>
      <path d="M18.9 2H22l-6.8 7.8L23 22h-6.2l-4.8-6.3L6.4 22H3.3l7.3-8.3L1 2h6.3l4.4 5.8L18.9 2Zm-1.1 18h1.7L6.3 3.9H4.5L17.8 20Z" />
    </svg>
  );
}

export function FollowOnX() {
  return (
    <a href={X_PROFILE} target="_blank" rel="noopener noreferrer"
      className="inline-flex shrink-0 items-center gap-1 rounded-full bg-accent px-4 py-2 text-[13.5px] font-semibold text-on-accent hover:bg-accent-hover">
      Follow on X <ArrowUpRight className="h-3.5 w-3.5" />
    </a>
  );
}

function Meta({ p }: { p: XPost }) {
  const tag = tagOf(p.text);
  return (
    <span className="flex items-center gap-2 text-[12.5px] text-muted">
      {tag && <span className="rounded-full border border-border-strong px-2 py-px text-[11px] font-semibold text-text-2">{tag}</span>}
      <time dateTime={p.at}>{when(p.at)}</time>
    </span>
  );
}

// One post as a card: the chart on top when it has one (Home's row).
export function XCard({ p }: { p: XPost }) {
  return (
    <a href={p.url} target="_blank" rel="noopener noreferrer"
      className="card group flex flex-col overflow-hidden transition-colors hover:border-border-strong">
      {p.image && <img src={small(p.image)} alt="Chart attached to the post" loading="lazy" className="aspect-[16/10] w-full bg-white object-cover" />}
      <span className="flex flex-1 flex-col px-4 pb-4 pt-3.5">
        <Meta p={p} />
        <span className={cn("mt-1.5 whitespace-pre-line text-[14px] leading-relaxed text-text", p.image ? "line-clamp-5" : "line-clamp-[10]")}>{p.text}</span>
        <span className="mt-auto pt-2 text-[12.5px] font-semibold text-accent group-hover:text-accent-hover">View on X ↗</span>
      </span>
    </a>
  );
}

// About's feed: the 5 newest, then "Show 5 more" (the export keeps 10).
export function XFeedCard() {
  const posts = useXFeed().data ?? [];
  const [open, setOpen] = useState(false);
  if (!posts.length) return null;
  return (
    <section aria-label="On X" className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4 md:px-[26px]">
        <div className="flex items-center gap-3">
          <img src="/team/ashleyn.png" alt="" className="h-11 w-11 rounded-full object-cover object-[40%_30%]" />
          <div>
            <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-accent"><XLogo className="h-3.5 w-3.5" />On X</div>
            <div className="font-bold text-text">Ashleyn Castelino <span className="font-normal text-muted">@AshleynCas46131</span></div>
          </div>
        </div>
        <FollowOnX />
      </div>
      <div className="divide-y divide-border">
        {posts.slice(0, open ? 10 : 5).map((p) => (
          <a key={p.id} href={p.url} target="_blank" rel="noopener noreferrer"
            className={cn("group grid gap-4 px-5 py-4 hover:bg-surface-3/50 md:px-[26px]", p.image && "md:grid-cols-[1fr_210px]")}>
            <span className="min-w-0">
              <Meta p={p} />
              <span className="mt-1.5 block whitespace-pre-line text-[14.5px] leading-relaxed text-text">{p.text}</span>
              <span className="mt-2 block text-[12.5px] font-semibold text-accent group-hover:text-accent-hover">View on X ↗</span>
            </span>
            {p.image && <img src={small(p.image)} alt="Chart attached to the post" loading="lazy" className="aspect-[16/10] w-full rounded-[10px] border border-border bg-white object-cover md:w-[210px]" />}
          </a>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3.5 text-[12.5px] text-muted md:px-[26px]">
        <span>The newest posts, refreshed every time the site updates. Replies are left out.</span>
        {posts.length > 5 && (
          <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
            className="rounded-full border border-border-strong px-4 py-1.5 text-[13px] font-semibold text-text hover:border-accent">
            {open ? "Show fewer" : `Show ${Math.min(5, posts.length - 5)} more`}
          </button>
        )}
      </div>
    </section>
  );
}
