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
import { fetchSyncSnapshot } from "../services/snapshot.service";

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
      // Payment already committed on the server. A secondary read failure must
      // not appear as a failed purchase and must never trigger a new payment.
      await Promise.allSettled([
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshot.current(globalId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.panels.summary(globalId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.panels.all(globalId),
          // Portfolio may be inactive; refresh cached pages for next open.
          refetchType: "all",
        }),
      ]);

      if (!globalId) return;
      try {
        // Explicitly replace the owner-bound balance snapshot with an
        // authoritative post-commit API read, even with persistent UI caches.
        const confirmed = await fetchSyncSnapshot();
        if (confirmed.profile.global_id !== globalId) return;
        queryClient.setQueryData(
          queryKeys.snapshot.current(globalId),
          confirmed,
        );
      } catch {
        // Preserve a valid paid result; the existing manual Refresh action
        // can safely retry only this read without charging the user again.
        try {
          await queryClient.invalidateQueries({
            queryKey: queryKeys.snapshot.current(globalId),
            refetchType: "none",
          });
        } catch { /* Cache invalidation is nonfinancial. */ }
      }
    },
  });
}
