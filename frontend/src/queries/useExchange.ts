import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {
  convertExchange,
  getExchangePreview,
} from "../services/exchange.service";
import { queryKeys } from "./queryKeys";
import { fetchSyncSnapshot, type SyncSnapshot } from "../services/snapshot.service";

export function useExchangePreview(enabled = true) {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: queryKeys.exchange.preview(globalId),
    enabled: Boolean(globalId) && enabled,
    queryFn: getExchangePreview,
    // One server-confirmed available_kwh source for Energy and Exchange.
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    refetchOnReconnect: "always",
    refetchInterval: globalId ? 30_000 : false,
  });
}

export function useExchangeConvert() {
  const globalId = useAuthOwnerGlobalId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: convertExchange,
    onSuccess: async (receipt) => {
      // The exchange has already committed: never report a successful
      // financial operation as failed because its display refresh failed.
      const snapshotKey = queryKeys.snapshot.current(globalId);
      if (globalId) {
        try {
          // Stop any pre-commit snapshot from overwriting the confirmed credit.
          await queryClient.cancelQueries({ queryKey: snapshotKey });
          queryClient.setQueryData<SyncSnapshot>(snapshotKey, (previous) => {
            if (!previous || previous.profile.global_id !== globalId) {
              return previous;
            }
            // The conversion receipt contains authoritative new balances.
            return {
              ...previous,
              profile: {
                ...previous.profile,
                main_balance: receipt.new__main__balance,
                available_kwh: receipt.new_available_kwh,
              },
            };
          });
        } catch {
          // A failed display-cache update cannot undo the committed exchange.
        }
      }

      try {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.exchange.preview(globalId),
        });
      } catch {
        // Preview is a read-only convenience, not the transfer outcome.
      }

      if (!globalId) return;
      try {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.account.current(globalId),
          refetchType: "all",
        });
      } catch { /* Account balance refresh is read-only. */ }
      try {
        const confirmed = await fetchSyncSnapshot();
        if (confirmed.profile.global_id !== globalId) return;
        queryClient.setQueryData(snapshotKey, confirmed);
      } catch {
        // Retry is read-only; the next Refresh button can reconcile the
        // snapshot without issuing any further financial transaction.
        try {
          await queryClient.invalidateQueries({
            queryKey: snapshotKey,
            refetchType: "none",
          });
        } catch { /* Nonfinancial cache invalidation is best effort. */ }
      }
    },
  });
}
