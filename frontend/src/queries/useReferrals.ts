import {
  useInfiniteQuery,
  useQuery,
} from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {
  getReferralStats,
  getReferralsPage,
  type ReferralTab,
} from "../services/referrals.service";
import { queryKeys } from "./queryKeys";

export function useReferralStats() {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: queryKeys.referrals.stats(globalId),
    enabled: Boolean(globalId),
    queryFn: ({ signal }) => getReferralStats(signal),
    staleTime: 30_000,
  });
}

export function useReferralList(tab: ReferralTab) {
  const globalId = useAuthOwnerGlobalId();
  return useInfiniteQuery({
    queryKey: queryKeys.referrals.list(globalId, tab),
    enabled: Boolean(globalId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      getReferralsPage({ tab, cursor: pageParam, signal }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}
