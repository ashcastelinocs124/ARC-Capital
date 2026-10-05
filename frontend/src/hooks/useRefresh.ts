import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchRefreshStatus, startRefresh, type RefreshStatus } from "@/api/refresh";

// Polls every 2s while a refresh runs; when it finishes, every dashboard query refetches.
export function useRefresh() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["refresh_status"],
    queryFn: fetchRefreshStatus,
    refetchInterval: (q) => ((q.state.data as RefreshStatus | undefined)?.running ? 2000 : false),
    refetchIntervalInBackground: true, // keep polling when the tab isn't focused, or the button sticks on "Refreshing"
  });
  const start = useMutation({
    mutationFn: startRefresh,
    onSettled: () => qc.invalidateQueries({ queryKey: ["refresh_status"] }),
  });

  const wasRunning = useRef(false);
  const running = !!status.data?.running;
  useEffect(() => {
    if (wasRunning.current && !running) qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "refresh_status" });
    wasRunning.current = running;
  }, [running, qc]);

  return { status: status.data, running, start: () => start.mutate(), starting: start.isPending };
}
