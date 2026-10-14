import { useQuery } from "@tanstack/react-query";
import { fetchThemeHistory, fetchThemeRun } from "@/api/endpoints";

export const useThemeHistory = () =>
  useQuery({ queryKey: ["theme_history"], queryFn: fetchThemeHistory, retry: false });
export const useThemeRun = (run: string | null) =>
  useQuery({ queryKey: ["theme_run", run], queryFn: () => fetchThemeRun(run), retry: false });
