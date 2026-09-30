import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import PortfolioPage from "./pages/PortfolioPage";
import MacroPage from "./pages/MacroPage";
import ResearchPage from "./pages/ResearchPage";
import RiskPage from "./pages/RiskPage";
import AgentsPage from "./pages/AgentsPage";
import DeepResearchPage from "./pages/DeepResearchPage";
import UpdatesPage from "./pages/UpdatesPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/portfolio" replace />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/macro" element={<MacroPage />} />
        <Route path="/research" element={<ResearchPage />} />
        <Route path="/deep-research" element={<DeepResearchPage />} />
        <Route path="/updates" element={<UpdatesPage />} />
        <Route path="/risk" element={<RiskPage />} />
        <Route path="/agents" element={<AgentsPage />} />
      </Routes>
    </AppShell>
  );
}
