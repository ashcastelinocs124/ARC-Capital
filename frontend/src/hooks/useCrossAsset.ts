import { useQuery } from "@tanstack/react-query";
import { fetchCrossAsset } from "@/api/endpoints";

export function useCrossAsset() {
  return useQuery({ queryKey: ["cross-asset"], queryFn: fetchCrossAsset, refetchInterval: 60_000 });
}
