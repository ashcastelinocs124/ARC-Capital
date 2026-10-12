import { useQuery } from "@tanstack/react-query";
import { fetchAgentCatalog } from "@/api/endpoints";

// admin = the full catalog from the password-gated /api/admin/ path; otherwise the public high-level one
export const useAgentCatalog = (admin = false) =>
  useQuery({ queryKey: ["agent_catalog", admin], queryFn: () => fetchAgentCatalog(admin), staleTime: 60_000 });
