import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import PortfolioPage from "./pages/PortfolioPage";
import ModelsPage from "./pages/ModelsPage";
import MacroPage from "./pages/MacroPage";
import ResearchPage from "./pages/ResearchPage";
import RiskPage from "./pages/RiskPage";
import AgentsPage from "./pages/AgentsPage";
import DeepResearchPage from "./pages/DeepResearchPage";
import UpdatesPage from "./pages/UpdatesPage";
import { HOME, pageEnabled } from "./pages/visibility";

const PAGES: [string, React.ReactNode][] = [
  ["/portfolio", <PortfolioPage />],
  ["/models", <ModelsPage />],
  ["/macro", <MacroPage />],
  ["/research", <ResearchPage />],
  ["/deep-research", <DeepResearchPage />],
  ["/updates", <UpdatesPage />],
  ["/risk", <RiskPage />],
  ["/agents", <AgentsPage />],
];

export default function App() {
  return (
    <AppShell>
      <Routes>
        {PAGES.filter(([path]) => pageEnabled(path)).map(([path, el]) => (
          <Route key={path} path={path} element={el} />
        ))}
        <Route path="/sector-sentiment" element={<Navigate to="/models" replace />} />
        <Route path="*" element={<Navigate to={HOME} replace />} />
      </Routes>
    </AppShell>
  );
}
