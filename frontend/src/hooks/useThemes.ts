import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { fetchThemeHistory, fetchThemePosts, fetchThemeRun } from "@/api/endpoints";

export const useThemePosts = () => useQuery({ queryKey: ["theme_posts"], queryFn: fetchThemePosts, retry: false });
export const useThemeHistory = () => useQuery({ queryKey: ["theme_history"], queryFn: fetchThemeHistory, retry: false });
// keepPreviousData: switching days keeps the card up instead of blanking it while the run loads
export const useThemeRun = (run: string | null) =>
  useQuery({ queryKey: ["theme_run", run], queryFn: () => fetchThemeRun(run), retry: false, placeholderData: keepPreviousData });
