import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

// Below md the sidebar becomes a drawer opened from the top bar's menu button.
export function AppShell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setMenuOpen(false), [pathname]);

  return (
    <div className="flex h-dvh bg-surface-2">
      <div className="hidden md:block h-full">
        <Sidebar />
      </div>
      {menuOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMenuOpen(false)} />
          <div className="relative h-full w-60 shadow-xl">
            <Sidebar collapsible={false} />
          </div>
        </div>
      )}
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar onMenu={() => setMenuOpen(true)} />
        <main className="flex-1 overflow-auto">
          {children}
          <Disclaimer />
        </main>
      </div>
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
      from its use.
    </footer>
  );
}
