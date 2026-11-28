import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {
  getMyRankWithTop,
  getRankContext,
  getRankTopPage,
} from "../services/ranks.service";
import { queryKeys } from "./queryKeys";

export function useMyRankWithTop(_globalId: string | null) {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: queryKeys.ranks.myPlusTop(globalId),
    enabled: Boolean(globalId),
    queryFn: ({ signal }) => getMyRankWithTop(signal),
    staleTime: 30_000,
  });
}

export function useRankTopPages(
  _globalId: string | null,
  firstCursor: string | null | undefined,
) {
  const globalId = useAuthOwnerGlobalId();
  return useInfiniteQuery({
    queryKey: queryKeys.ranks.top(globalId),
    enabled: Boolean(firstCursor && globalId),
    initialPageParam: firstCursor ?? null,
    queryFn: ({ pageParam, signal }) => {
      if (!pageParam) {
        return Promise.resolve({
          snapshot_at: "",
          items: [],
          next_cursor: null,
        });
      }
      return getRankTopPage({ cursor: pageParam, signal });
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useRankContext() {
  const globalId = useAuthOwnerGlobalId();
  return useMutation({
    mutationFn: () => getRankContext(),
  });
}

export function useRefreshRanks(_globalId: string | null) {
  const globalId = useAuthOwnerGlobalId();
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: queryKeys.ranks.myPlusTop(globalId),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.ranks.top(globalId),
      }),
    ]);
  };
}
