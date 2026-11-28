import { useMutation, useQuery } from "@tanstack/react-query";

import {
  createHubEfhcHandoff,
  getPublicHubLinks,
} from "../services/hub.service";

export function useHubEfhcHandoff() {
  return useMutation({
    mutationFn: createHubEfhcHandoff,
  });
}

export function usePublicHubLinks() {
  return useQuery({
    queryKey: ["hub", "links", "public"],
    queryFn: getPublicHubLinks,
    retry: false,
    staleTime: 30_000,
  });
}
