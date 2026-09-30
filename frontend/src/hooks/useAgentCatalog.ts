import { useQuery } from "@tanstack/react-query";
import { fetchAgentCatalog } from "@/api/endpoints";

export const useAgentCatalog = () =>
  useQuery({ queryKey: ["agent_catalog"], queryFn: fetchAgentCatalog, staleTime: 60_000 });
