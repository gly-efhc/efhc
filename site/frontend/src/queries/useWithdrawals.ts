import {
  useInfiniteQuery,
  type InfiniteData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {
  cancelWithdrawRequest,
  createWithdrawRequest,
  getWalletBalanceHistory,
  getWithdrawDetail,
  getWithdrawOutcome,
  getWithdrawalsPage,
  type WithdrawItem,
} from "../services/withdrawals.service";
import type { GlobalId } from "../types/identity";
import { queryKeys } from "./queryKeys";
import type { DbId } from "../types/db-id";
import type { WithdrawPageResponse } from "../lib/api/generated/economicUserSeams";

export function useWithdrawalsPage(args: {
  statusFilter: string;
}) {
  const globalId = useAuthOwnerGlobalId();
  return useInfiniteQuery({
    queryKey: queryKeys.withdrawals.list(
      globalId,
      args.statusFilter,
    ),
    enabled: Boolean(globalId),
    staleTime: 10_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => getWithdrawalsPage({
      cursor: pageParam,
      statusFilter: args.statusFilter,
      signal,
    }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useWithdrawDetail(requestId: DbId | null) {
  return useQuery({
    queryKey: queryKeys.withdrawals.detail(requestId),
    enabled: Boolean(requestId),
    queryFn: ({ signal }) => {
      if (!requestId) throw new Error("WITHDRAW_REQUEST_ID_REQUIRED");
      return getWithdrawDetail(requestId, signal);
    },
  });
}

export function useWalletBalanceHistory() {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: queryKeys.withdrawals.history(globalId),
    enabled: Boolean(globalId),
    queryFn: ({ signal }) => getWalletBalanceHistory(5, signal),
  });
}

export function useWithdrawOutcome(requestId: DbId | null) {
  return useQuery({
    queryKey: queryKeys.withdrawals.outcome(requestId),
    enabled: Boolean(requestId),
    queryFn: ({ signal }) => {
      if (!requestId) throw new Error("WITHDRAW_REQUEST_ID_REQUIRED");
      return getWithdrawOutcome(requestId, signal);
    },
  });
}

async function invalidateWithdrawQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  globalId: GlobalId | null,
  requestId?: DbId,
) {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: queryKeys.withdrawals.all(globalId),
      refetchType: "none",
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.snapshot.current(globalId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.profile.balanceHistory(globalId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.profile.withdrawHistory(globalId),
    }),
    requestId
      ? queryClient.invalidateQueries({
        queryKey: queryKeys.withdrawals.detail(requestId),
      })
      : Promise.resolve(),
  ]);
}

function reflectConfirmedRequest(
  queryClient: ReturnType<typeof useQueryClient>,
  globalId: GlobalId | null,
  item: WithdrawItem,
  isCreated: boolean,
): void {
  type Pages = InfiniteData<WithdrawPageResponse, string | null>;
  queryClient.setQueryData<Pages>(
    queryKeys.withdrawals.list(globalId, "all"),
    (previous) => {
      if (!previous?.pages.length) return previous;
      const exists = previous.pages.some((page) =>
        page.items.some((request) => request.id === item.id),
      );
      const pages = previous.pages.map((page) => ({
        ...page,
        items: page.items.map((request) => request.id === item.id ? item : request),
      }));
      if (isCreated && !exists) {
        pages[0] = { ...pages[0], items: [item, ...pages[0].items] };
      }
      return { ...previous, pages };
    },
  );
}

export function useCreateWithdrawRequest() {
  const globalId = useAuthOwnerGlobalId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createWithdrawRequest,
    onSuccess: async (result) => {
      reflectConfirmedRequest(queryClient, globalId, result, true);
      await invalidateWithdrawQueries(
        queryClient,
        globalId,
        result.id,
      );
    },
  });
}

export function useCancelWithdrawRequest() {
  const globalId = useAuthOwnerGlobalId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: cancelWithdrawRequest,
    onSuccess: async (result) => {
      reflectConfirmedRequest(queryClient, globalId, result, false);
      await invalidateWithdrawQueries(
        queryClient,
        globalId,
        result.id,
      );
    },
  });
}
