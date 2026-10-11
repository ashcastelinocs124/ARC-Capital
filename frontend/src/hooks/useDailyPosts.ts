import { useQuery } from "@tanstack/react-query";
import { fetchDailyPosts } from "@/api/endpoints";

export function useDailyPosts() {
  return useQuery({ queryKey: ["daily-posts"], queryFn: fetchDailyPosts, staleTime: 10 * 60_000 });
}
