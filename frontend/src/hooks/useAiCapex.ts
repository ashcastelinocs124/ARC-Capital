import { useQuery } from "@tanstack/react-query";
import { fetchAiCapex } from "@/api/aiCapex";

export const useAiCapex = () => useQuery({ queryKey: ["ai-capex"], queryFn: fetchAiCapex, refetchInterval: 10 * 60_000 });
