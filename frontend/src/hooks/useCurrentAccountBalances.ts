import { useQuery } from "@tanstack/react-query";
import {
  useAuthOwnerGlobalId,
  useAuthSessionController,
} from "../auth/AuthSessionProvider";
import { queryKeys } from "../queries/queryKeys";
import { readCurrentAccountBalances } from "../services/accountBalance.service";

/** Revalidate financial truth independently from persisted energy snapshots. */
export function useCurrentAccountBalances() {
  const owner = useAuthOwnerGlobalId();
  const auth = useAuthSessionController();
  const signed = auth.status === "authenticated" && Boolean(owner);
  return useQuery({
    queryKey: queryKeys.account.current(owner),
    enabled: signed,
    // Financial balances are never persisted to localStorage as query truth.
    // A fresh signed read is mandatory on every mount, focus and reconnect.
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    refetchOnReconnect: "always",
    refetchInterval: signed ? 30_000 : false,
    queryFn: async ({ signal }) => {
      const result = await readCurrentAccountBalances(signal);
      if (!owner || result.global_id !== owner) {
        throw new Error("ACCOUNT_BALANCE_OWNER_MISMATCH");
      }
      return result;
    },
  });
}
