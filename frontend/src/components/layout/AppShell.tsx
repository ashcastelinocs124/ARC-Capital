import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { TopBar } from "./TopBar";
import { TopNav } from "./TopNav";

export function AppShell({ children }: { children: React.ReactNode }) {
  // <main> is the scroller, so a new page would otherwise open at the old page's scroll position.
  const main = useRef<HTMLElement>(null);
  const { pathname, hash } = useLocation();
  useEffect(() => {
    main.current?.scrollTo(0, 0); // braces: scrollTo can return a Promise, and an effect may only return a cleanup
  }, [pathname]);
  // A #hash (nav links such as /models#model-adoption) scrolls to that card once it has rendered;
  // cards wait on data, so look for it for up to 3 s.
  useEffect(() => {
    if (!hash) return;
    let tries = 0;
    const t = setInterval(() => {
      const el = document.getElementById(decodeURIComponent(hash.slice(1)));
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      if (el || ++tries > 30) clearInterval(t);
    }, 100);
    return () => clearInterval(t);
  }, [pathname, hash]);
  return (
    <div className="flex flex-col h-dvh bg-surface-2">
      <TopBar />
      <TopNav />
      <main ref={main} className="flex-1 overflow-auto">
        {children}
        <Disclaimer />
      </main>
    </div>
  );
}

// Shown under every page, including the public site.
function Disclaimer() {
  return (
    <footer className="px-4 md:px-8 pb-6 pt-2 text-[11px] leading-relaxed text-muted max-w-5xl">
      <b className="font-semibold text-text-2">Not investment advice.</b> ARC Research is for informational and
      educational purposes only. Nothing here is investment, financial, legal or tax advice, or an offer or
      solicitation to buy or sell any security. Figures come from simulated models, AI-generated text and
      third-party data that may be incomplete, delayed or wrong, and past performance does not predict future
      results. Do your own research or consult a licensed professional before making any investment decision.
      You use this site at your own risk; ARC Research and its authors accept no liability for any loss arising
      from its use. <Link to="/about" className="font-semibold text-text-2 underline hover:text-text">About ARC</Link>
    </footer>
  );
}
