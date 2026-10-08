import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import ModelsPage from "./pages/ModelsPage";
import MacroPage from "./pages/MacroPage";
import AgentsPage from "./pages/AgentsPage";
import DeepResearchPage from "./pages/DeepResearchPage";
import UpdatesPage from "./pages/UpdatesPage";
import DocsPage from "./pages/DocsPage";

const HOME = "/models";

const PAGES: [string, React.ReactNode][] = [
  ["/models", <ModelsPage />],
  ["/macro", <MacroPage />],
  ["/deep-research", <DeepResearchPage />],
  ["/updates", <UpdatesPage />],
  ["/agents", <AgentsPage />],
  ["/docs", <DocsPage />],
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
