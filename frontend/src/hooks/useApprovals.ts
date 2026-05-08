import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveItem,
  fetchApprovalDetail,
  fetchApprovalHistory,
  fetchApprovalMetrics,
  fetchApprovalQueueFull,
  rejectItem,
} from "@/api/endpoints";

export function useApprovalMetrics() {
  return useQuery({
    queryKey: ["approval_metrics"],
    queryFn: fetchApprovalMetrics,
    refetchInterval: 5_000,
  });
}

export function useApprovalQueue() {
  return useQuery({
    queryKey: ["approval_queue_full"],
    queryFn: fetchApprovalQueueFull,
    refetchInterval: 5_000,
  });
}

export function useApprovalHistory() {
  return useQuery({
    queryKey: ["approval_history"],
    queryFn: fetchApprovalHistory,
    refetchInterval: 30_000,
  });
}

export function useApprovalDetail(entryId: string | null) {
  return useQuery({
    queryKey: ["approval_detail", entryId],
    queryFn: () => fetchApprovalDetail(entryId!),
    enabled: !!entryId,
  });
}

export function useApproveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, notes }: { entryId: string; notes: string }) =>
      approveItem(entryId, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approval_queue_full"] });
      qc.invalidateQueries({ queryKey: ["approval_metrics"] });
      qc.invalidateQueries({ queryKey: ["approval_history"] });
    },
  });
}

export function useRejectMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, notes }: { entryId: string; notes: string }) =>
      rejectItem(entryId, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approval_queue_full"] });
      qc.invalidateQueries({ queryKey: ["approval_metrics"] });
      qc.invalidateQueries({ queryKey: ["approval_history"] });
    },
  });
}
