import { useQuery } from "@tanstack/react-query";

import { getSupportLinks } from "../services/support.service";

export function useSupportLinks() {
  return useQuery({
    queryKey: ["hub", "support-links"],
    queryFn: getSupportLinks,
    retry: false,
    staleTime: 30_000,
  });
}
