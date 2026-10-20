import { useQuery } from "@tanstack/react-query";
import { fetchXFeed } from "@/api/endpoints";

export function useXFeed() {
  return useQuery({ queryKey: ["x-feed"], queryFn: fetchXFeed, staleTime: 10 * 60_000 });
}
