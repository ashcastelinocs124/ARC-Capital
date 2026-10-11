import { useQuery } from "@tanstack/react-query";
import { fetchVideos } from "@/api/endpoints";

export function useVideos() {
  return useQuery({ queryKey: ["videos"], queryFn: fetchVideos, staleTime: 10 * 60_000 });
}
