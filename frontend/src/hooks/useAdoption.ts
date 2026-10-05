import { useQuery } from "@tanstack/react-query";
import { fetchAdoptionCompanies, fetchAdoptionSummary, type Bucket } from "@/api/adoption";

export const useAdoptionSummary = () =>
  useQuery({ queryKey: ["adoption_summary"], queryFn: fetchAdoptionSummary, refetchInterval: 5 * 60_000 });

export const useAdoptionCompanies = (sector: string | null, bucket: Bucket) =>
  useQuery({
    queryKey: ["adoption_companies", sector, bucket],
    queryFn: () => fetchAdoptionCompanies(sector as string, bucket),
    enabled: !!sector,
  });
