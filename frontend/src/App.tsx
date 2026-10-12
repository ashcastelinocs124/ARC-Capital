import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import HomePage from "./pages/HomePage";
import ModelsPage from "./pages/ModelsPage";
import MacroPage from "./pages/MacroPage";
import AgentsPage from "./pages/AgentsPage";
import DeepResearchPage from "./pages/DeepResearchPage";
import UpdatesPage from "./pages/UpdatesPage";
import DocsPage from "./pages/DocsPage";
import VideosPage from "./pages/VideosPage";
import AdminPage from "./pages/AdminPage";

const HOME = "/";

const PAGES: [string, React.ReactNode][] = [
  ["/", <HomePage />],
  ["/models", <ModelsPage />],
  ["/macro", <MacroPage />],
  ["/deep-research", <DeepResearchPage />],
  ["/updates", <UpdatesPage />],
  ["/videos", <VideosPage />],
  ["/agents", <AgentsPage />],
  ["/docs", <DocsPage />],
  ["/admin", <AdminPage />], // not in the tabs; password-gated on the public site (middleware.ts)
];

export default function App() {
  return (
    <AppShell>
      <Routes>
        {PAGES.map(([path, el]) => (
          <Route key={path} path={path} element={el} />
        ))}
        <Route path="/sector-sentiment" element={<Navigate to="/models" replace />} />
        <Route path="*" element={<Navigate to={HOME} replace />} />
      </Routes>
    </AppShell>
  );
}
