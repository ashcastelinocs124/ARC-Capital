import { useQuery } from "@tanstack/react-query";
import {
  fetchAgentBear,
  fetchAgentBull,
  fetchAgentCurator,
  fetchAgentExpressions,
  fetchAgentGuard,
  fetchAgentHypotheses,
  fetchAgentResearch,
  fetchAgentSummary,
  fetchAgentTriggers,
  fetchAgentVerdicts,
  fetchAgentWarnings,
  fetchAgentWorldState,
  fetchGuardDecisions,
  fetchVerdicts,
} from "@/api/endpoints";

export const useVerdicts = () =>
  useQuery({ queryKey: ["verdicts"], queryFn: fetchVerdicts, refetchInterval: 60_000 });

export const useGuardDecisions = () =>
  useQuery({ queryKey: ["guard_decisions"], queryFn: fetchGuardDecisions, refetchInterval: 60_000 });

const POLL = 30_000;

export const useAgentSummary = () =>
  useQuery({ queryKey: ["agent_summary"], queryFn: fetchAgentSummary, refetchInterval: POLL });
export const useAgentTriggers = () =>
  useQuery({ queryKey: ["agent_triggers"], queryFn: fetchAgentTriggers, refetchInterval: POLL });
export const useAgentWorldState = () =>
  useQuery({ queryKey: ["agent_world_state"], queryFn: fetchAgentWorldState, refetchInterval: POLL });
export const useAgentHypotheses = () =>
  useQuery({ queryKey: ["agent_hypotheses"], queryFn: fetchAgentHypotheses, refetchInterval: POLL });
export const useAgentExpressions = () =>
  useQuery({ queryKey: ["agent_expressions"], queryFn: fetchAgentExpressions, refetchInterval: POLL });
export const useAgentResearch = () =>
  useQuery({ queryKey: ["agent_research"], queryFn: fetchAgentResearch, refetchInterval: POLL });
export const useAgentBull = () =>
  useQuery({ queryKey: ["agent_bull"], queryFn: fetchAgentBull, refetchInterval: POLL });
export const useAgentBear = () =>
  useQuery({ queryKey: ["agent_bear"], queryFn: fetchAgentBear, refetchInterval: POLL });
export const useAgentVerdicts = () =>
  useQuery({ queryKey: ["agent_verdicts"], queryFn: fetchAgentVerdicts, refetchInterval: POLL });
export const useAgentGuard = () =>
  useQuery({ queryKey: ["agent_guard"], queryFn: fetchAgentGuard, refetchInterval: POLL });
export const useAgentWarnings = () =>
  useQuery({ queryKey: ["agent_warnings"], queryFn: fetchAgentWarnings, refetchInterval: POLL });
export const useAgentCurator = () =>
  useQuery({ queryKey: ["agent_curator"], queryFn: fetchAgentCurator, refetchInterval: 5 * 60_000 });
