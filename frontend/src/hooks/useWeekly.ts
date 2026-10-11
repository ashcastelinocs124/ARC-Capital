import { useQuery } from "@tanstack/react-query";
import { fetchWeekly, fetchWeeklyHistory, fetchWeeklyStatus } from "@/api/endpoints";

const ACTIVE = new Set(["planning", "researching", "grilling", "writing", "guarding", "charting"]);

export const useWeeklyStatus = () =>
  useQuery({
    queryKey: ["weekly_status"],
    queryFn: fetchWeeklyStatus,
    refetchInterval: (q) => (q.state.data && ACTIVE.has(q.state.data.stage) ? 5_000 : 60_000),
  });
export const useWeeklyHistory = () =>
  useQuery({ queryKey: ["weekly_history"], queryFn: fetchWeeklyHistory, retry: false });
export const useWeekly = (week: string | null, enabled = true) =>
  useQuery({ queryKey: ["weekly", week], queryFn: () => fetchWeekly(week), retry: false, enabled });
