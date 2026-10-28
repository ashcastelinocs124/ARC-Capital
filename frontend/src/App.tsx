import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import HomePage from "./pages/HomePage";
import MacroPage from "./pages/MacroPage";
import PipelinesPage from "./pages/PipelinesPage";
import DeepResearchPage from "./pages/DeepResearchPage";
import UpdatesPage from "./pages/UpdatesPage";
import DocsPage from "./pages/DocsPage";
import VideosPage from "./pages/VideosPage";
import AdminPage from "./pages/AdminPage";
import AdminLoginPage from "./pages/AdminLoginPage";
import AboutPage from "./pages/AboutPage";
import ResourcesPage from "./pages/ResourcesPage";
import SectionPage from "./pages/SectionPage";
import ThemesPage from "./pages/ThemesPage";
import AiCapexPage from "./pages/dashboards/AiCapexPage";

const HOME = "/";

const PAGES: [string, React.ReactNode][] = [
  ["/", <HomePage />],
  ["/macro", <MacroPage />],
  ["/deep-research", <DeepResearchPage />],
  ["/updates", <UpdatesPage />],
  ["/themes", <ThemesPage />],
  ["/videos", <VideosPage />],
  // ponytail: Models also lists posts still in the old AI Update section; drop that slug once they're all moved
  ["/ai/models", <SectionPage slugs={["ai-models", "artificial-intelligence-update"]} kicker="AI · Models" title="Models, labs and releases" blurb="Every AI Models post, newest first." />],
  ["/ai/chips", <SectionPage slugs={["semis-chips"]} kicker="AI · Semis & Chips" title="Semis, chips and the compute supply chain" blurb="Every Semis & Chips post, newest first." />],
  ["/special-topics", <SectionPage slugs={["special-topics"]} kicker="Special Topics" title="Deeper dives and presentations" blurb="Every Special Topics post, newest first." />],
  ["/dashboards/ai-capex", <AiCapexPage />],
  ["/agents", <PipelinesPage />],
  ["/docs", <DocsPage />],
  ["/resources", <ResourcesPage />],
  ["/about", <AboutPage />],
];

export default function App() {
  const path = useLocation().pathname.replace(/\/$/, "");
  // the admin sign-in page and the admin console stand alone, without the site's top bar and footer;
  // both are password-gated on the public site (middleware.ts)
  if (path === "/admin/login") return <AdminLoginPage />;
  if (path === "/admin" || path.startsWith("/admin/")) return <AdminPage />;
  return (
    <AppShell>
      <Routes>
        {PAGES.map(([path, el]) => (
          <Route key={path} path={path} element={el} />
        ))}
        {/* the models went admin-only on 2026-10-15; the one public card, Fear & Greed, is on Radar */}
        <Route path="/ai" element={<Navigate to="/ai/models" replace />} />
        {/* ponytail: one dashboard so far, so /dashboards is it; a list page when there's a second */}
        <Route path="/dashboards" element={<Navigate to="/dashboards/ai-capex" replace />} />
        <Route path="/models" element={<Navigate to="/macro#sector-sentiment" replace />} />
        <Route path="/sector-sentiment" element={<Navigate to="/macro#sector-sentiment" replace />} />
        <Route path="*" element={<Navigate to={HOME} replace />} />
      </Routes>
    </AppShell>
  );
}
