import { useQuery } from "@tanstack/react-query";
import { fetchModels } from "@/api/endpoints";

export const useModels = () =>
  useQuery({ queryKey: ["models"], queryFn: fetchModels, refetchInterval: 60_000 });
