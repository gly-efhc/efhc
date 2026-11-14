import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {
  deleteWallet,
  downloadProfileHistoryExport,
  type ProfileHistoryExportCategory,
  getProfileBalanceHistoryPage,
  getProfilePhotoSources,
  getProfileExchangeHistoryPage,
  getProfileWallets,
  getUnifiedProfileHistoryPage,
  getProfileWithdrawHistoryPage,
  makePrimaryWallet,
  type WalletsMeOut,
} from "../services/profile.service";
import { queryKeys } from "./queryKeys";
import type { DbId } from "../types/db-id";

export function useProfileWalletSnapshot() {
  return useMutation({
    mutationFn: () => getProfileWallets(),
  });
}

export function useUnifiedProfileHistoryPageLoader() {
  return useMutation({
    mutationFn: (cursor?: string | null) =>
      getUnifiedProfileHistoryPage({ cursor: cursor ?? null }),
  });
}

export function useProfileWithdrawHistoryPageLoader() {
  return useMutation({
    mutationFn: (cursor?: string | null) =>
      getProfileWithdrawHistoryPage({ cursor: cursor ?? null, limit: 20 }),
  });
}

export function useProfileWallets() {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: queryKeys.profile.wallets(globalId),
    enabled: Boolean(globalId),
    queryFn: ({ signal }) => getProfileWallets(signal),
    staleTime: 10_000,
  });
}

export function useProfileBalanceHistory(
  enabled: boolean,
) {
  const globalId = useAuthOwnerGlobalId();
  return useInfiniteQuery({
    queryKey: queryKeys.profile.balanceHistory(globalId),
    enabled: Boolean(globalId) && enabled,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => (
      getProfileBalanceHistoryPage({
        cursor: pageParam,
        limit: 50,
        signal,
      })
    ),
    getNextPageParam: (lastPage) => (
      lastPage.next_cursor ?? undefined
    ),
  });
}

export function useProfileExchangeHistory(
  enabled: boolean,
) {
  const globalId = useAuthOwnerGlobalId();
  return useInfiniteQuery({
    queryKey: queryKeys.profile.exchangeHistory(globalId),
    enabled: Boolean(globalId) && enabled,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => (
      getProfileExchangeHistoryPage({
        cursor: pageParam,
        limit: 50,
        signal,
      })
    ),
    getNextPageParam: (lastPage) => (
      lastPage.next_cursor ?? undefined
    ),
  });
}

export function useProfileWithdrawHistory(
  enabled: boolean,
) {
  const globalId = useAuthOwnerGlobalId();
  return useInfiniteQuery({
    queryKey: queryKeys.profile.withdrawHistory(globalId),
    enabled: Boolean(globalId) && enabled,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => (
      getProfileWithdrawHistoryPage({
        cursor: pageParam,
        limit: 50,
        signal,
      })
    ),
    getNextPageParam: (lastPage) => (
      lastPage.next_cursor ?? undefined
    ),
  });
}

export function useUnifiedProfileHistory(enabled: boolean) {
  const globalId = useAuthOwnerGlobalId();
  return useInfiniteQuery({
    queryKey: ["profile", "unified-history", globalId],
    enabled: Boolean(globalId) && enabled,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => (
      getUnifiedProfileHistoryPage({ cursor: pageParam, signal })
    ),
    getNextPageParam: (lastPage) => (
      lastPage.next_cursor ?? undefined
    ),
  });
}

type ProfileWalletAction =
  | { kind: "make-primary"; walletId: DbId }
  | { kind: "remove"; walletId: DbId };

export function useProfileWalletActions() {
  const globalId = useAuthOwnerGlobalId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (action: ProfileWalletAction) => {
      if (action.kind === "make-primary") {
        return await makePrimaryWallet(action.walletId);
      }
      return await deleteWallet(action.walletId);
    },
    onMutate: async (action) => {
      const queryKey = queryKeys.profile.wallets(globalId);
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<WalletsMeOut>(queryKey);

      if (previous && action.kind === "make-primary") {
        queryClient.setQueryData<WalletsMeOut>(queryKey, {
          ...previous,
          wallets: previous.wallets.map((wallet) => ({
            ...wallet,
            is_primary: wallet.id === action.walletId,
          })),
        });
      }

      return { previous, queryKey };
    },
    onError: (_error, _action, context) => {
      if (context?.previous) {
        queryClient.setQueryData(context.queryKey, context.previous);
      }
    },
    onSettled: async (_data, _error, _action, context) => {
      await queryClient.invalidateQueries({
        queryKey: context?.queryKey ?? queryKeys.profile.wallets(globalId),
      });
    },
  });
}

export function useProfilePhotoSources(enabled = true) {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: ["profile", globalId, "photo-sources"],
    enabled: Boolean(globalId) && enabled,
    queryFn: ({ signal }) => getProfilePhotoSources(signal),
    staleTime: 60_000,
  });
}

export function useProfileHistoryExport() {
  return useMutation({
    mutationFn: ({ format, category }: {
      format: "csv" | "xlsx";
      category: ProfileHistoryExportCategory;
    }) => downloadProfileHistoryExport(format, category),
  });
}

