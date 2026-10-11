import { useQuery } from "@tanstack/react-query";
import { fetchSectionPosts } from "@/api/endpoints";

export function useSectionPosts() {
  return useQuery({ queryKey: ["section-posts"], queryFn: fetchSectionPosts, staleTime: 10 * 60_000 });
}
