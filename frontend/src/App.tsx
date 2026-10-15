import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import HomePage from "./pages/HomePage";
import MacroPage from "./pages/MacroPage";
import AgentsPage from "./pages/AgentsPage";
import DeepResearchPage from "./pages/DeepResearchPage";
import UpdatesPage from "./pages/UpdatesPage";
import DocsPage from "./pages/DocsPage";
import VideosPage from "./pages/VideosPage";
import AdminPage from "./pages/AdminPage";
import AdminLoginPage from "./pages/AdminLoginPage";
import AboutPage from "./pages/AboutPage";
import SectionPage from "./pages/SectionPage";
import ThemesPage from "./pages/ThemesPage";

const HOME = "/";

const PAGES: [string, React.ReactNode][] = [
  ["/", <HomePage />],
  ["/macro", <MacroPage />],
  ["/deep-research", <DeepResearchPage />],
  ["/updates", <UpdatesPage />],
  ["/themes", <ThemesPage />],
  ["/videos", <VideosPage />],
  ["/ai", <SectionPage slug="artificial-intelligence-update" kicker="AI · AI Update" title="Models, chips and the AI stack" blurb="Every AI Update post, newest first." />],
  ["/special-topics", <SectionPage slug="special-topics" kicker="Special Topics" title="Deeper dives and presentations" blurb="Every Special Topics post, newest first." />],
  ["/agents", <AgentsPage />],
  ["/docs", <DocsPage />],
  ["/about", <AboutPage />],
  ["/admin", <AdminPage />], // not in the tabs; password-gated on the public site (middleware.ts)
];

export default function App() {
  // the admin sign-in page stands alone, without the site's top bar and footer
  if (useLocation().pathname.replace(/\/$/, "") === "/admin/login") return <AdminLoginPage />;
  return (
    <AppShell>
      <Routes>
        {PAGES.map(([path, el]) => (
          <Route key={path} path={path} element={el} />
        ))}
        {/* the models went admin-only on 2026-10-15; the one public card, Fear & Greed, is on Radar */}
        <Route path="/models" element={<Navigate to="/macro#sector-sentiment" replace />} />
        <Route path="/sector-sentiment" element={<Navigate to="/macro#sector-sentiment" replace />} />
        <Route path="*" element={<Navigate to={HOME} replace />} />
      </Routes>
    </AppShell>
  );
}
