import { useQuery } from "@tanstack/react-query";
import { fetchThemePosts } from "@/api/endpoints";

export const useThemePosts = () => useQuery({ queryKey: ["theme_posts"], queryFn: fetchThemePosts, retry: false });
