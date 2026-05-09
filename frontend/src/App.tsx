import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import ApprovalCenterPage from "./pages/ApprovalCenterPage";
import { ApprovalConsultPage } from "./pages/ApprovalConsultPage";
import PortfolioPage from "./pages/PortfolioPage";
import MacroPage from "./pages/MacroPage";
import ResearchPage from "./pages/ResearchPage";
import RiskPage from "./pages/RiskPage";
import AgentsPage from "./pages/AgentsPage";
import PersonasPage from "./pages/PersonasPage";
import RoomsPage from "./pages/RoomsPage";
import RoomChatPage from "./pages/RoomChatPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/portfolio" replace />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/macro" element={<MacroPage />} />
        <Route path="/research" element={<ResearchPage />} />
        <Route path="/risk" element={<RiskPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/personas" element={<PersonasPage />} />
        <Route path="/rooms" element={<RoomsPage />} />
        <Route path="/rooms/:roomId" element={<RoomChatPage />} />
        <Route path="/approvals" element={<ApprovalCenterPage />} />
        <Route path="/approvals/:entryId/consult" element={<ApprovalConsultPage />} />
      </Routes>
    </AppShell>
  );
}
