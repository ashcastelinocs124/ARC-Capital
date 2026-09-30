import { useQuery } from "@tanstack/react-query";
import { fetchLatestUpdate, fetchUpdateByDate, fetchUpdateHistory, fetchUpdateStatus } from "@/api/endpoints";

export const ACTIVE_STAGES = new Set(["checking", "refitting", "gating", "collecting", "writing", "guarding"]);

export const useUpdateStatus = () =>
  useQuery({
    queryKey: ["update_status"],
    queryFn: fetchUpdateStatus,
    refetchInterval: (q) => (q.state.data && ACTIVE_STAGES.has(q.state.data.stage) ? 3_000 : 30_000),
  });

// stage in the key so the briefing refetches the moment a run finishes
export const useLatestUpdate = (stage: string | undefined) =>
  useQuery({ queryKey: ["update_latest", stage], queryFn: fetchLatestUpdate, retry: false });

export const useUpdateHistory = (stage: string | undefined) =>
  useQuery({ queryKey: ["update_history", stage], queryFn: fetchUpdateHistory, retry: false });

export const useUpdateByDate = (day: string | null) =>
  useQuery({ queryKey: ["update_day", day], queryFn: () => fetchUpdateByDate(day as string), enabled: !!day, retry: false });
