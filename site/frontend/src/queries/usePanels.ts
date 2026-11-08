import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {
  activatePanel,
  getPanelsPage,
  getPanelsSummary,
  type PanelTab,
} from "../services/panels.service";
import { queryKeys } from "./queryKeys";

export function usePanelsSummary() {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: queryKeys.panels.summary(globalId),
    enabled: Boolean(globalId),
    queryFn: getPanelsSummary,
    staleTime: 10_000,
  });
}

export function usePanelsList(
  tab: PanelTab,
  sortDirection: "oldest" | "newest" = "oldest",
) {
  const globalId = useAuthOwnerGlobalId();
  return useInfiniteQuery({
    queryKey: [...queryKeys.panels.list(globalId, tab), sortDirection],
    enabled: Boolean(globalId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => getPanelsPage({ tab, cursor: pageParam, signal }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    refetchOnMount: false,
  });
}

export function usePanelActivation() {
  const globalId = useAuthOwnerGlobalId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: activatePanel,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshot.current(globalId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.panels.summary(globalId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.panels.all(globalId),
          // Portfolio is inactive on the activation route, and shared query
          // defaults disable refetch-on-mount. Refresh its cached pages now.
          refetchType: "all",
        }),
      ]);
    },
  });
}
