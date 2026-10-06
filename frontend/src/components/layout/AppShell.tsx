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
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
