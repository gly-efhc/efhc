import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  createBrowserShopAccessKey,
  createBrowserShopIntent,
  getBrowserShopBootstrap,
  getBrowserShopCatalog,
  getBrowserShopIntentStatus,
  getBrowserShopProfile,
  purchaseBrowserShopWithEfhc,
} from "../services/browserShop.service";
import { selectBrowserShop } from "../services/browserShopSelection.service";
import { queryKeys } from "./queryKeys";
import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import type { DbId } from "../types/db-id";

const TERMINAL = new Set([
  "CONFIRMED",
  "EXPIRED",
  "CANCELED",
  "FAILED",
]);

export function useBrowserShopSelect() {
  return useMutation({mutationFn:selectBrowserShop});
}

export function useBrowserShopAccessKey() {
  return useMutation({ mutationFn: createBrowserShopAccessKey });
}

export function useBrowserShopBootstrap(token: string) {
  return useQuery({
    queryKey: queryKeys.browserShop.bootstrap(token),
    enabled: Boolean(token),
    queryFn: () => getBrowserShopBootstrap(token),
    staleTime: 5_000,
  });
}

export function useBrowserShopCatalog() {
  return useQuery({
    queryKey: queryKeys.browserShop.catalog,
    queryFn: getBrowserShopCatalog,
    staleTime: 30_000,
  });
}

export function useBrowserShopProfile(token: string) {
  return useQuery({
    queryKey: queryKeys.browserShop.profile(token),
    enabled: Boolean(token),
    queryFn: () => getBrowserShopProfile(token),
    staleTime: 5_000,
  });
}

export function useBrowserShopIntentStatus(
  token: string,
  intentId: DbId | null,
) {
  return useQuery({
    queryKey: queryKeys.browserShop.intentStatus(token, intentId),
    enabled: Boolean(token && intentId),
    queryFn: () => {
      if (!intentId) throw new Error("BROWSER_SHOP_INTENT_ID_REQUIRED");
      return getBrowserShopIntentStatus({ token, intentId });
    },
    refetchInterval: (query) => {
      const raw = String(query.state.data?.status || "").toUpperCase();
      return TERMINAL.has(raw) ? false : 5_000;
    },
    refetchIntervalInBackground: true,
  });
}

export function useBrowserShopCreateIntent(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createBrowserShopIntent,
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.browserShop.bootstrap(token),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.browserShop.profile(token),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.browserShop.intentStatus(
            token,
            result.intent_id,
          ),
        }),
      ]);
    },
  });
}

export function useBrowserShopEfhcPurchase() {
  const queryClient = useQueryClient();
  const globalId = useAuthOwnerGlobalId();
  return useMutation({
    mutationFn: purchaseBrowserShopWithEfhc,
    onSuccess: async () => {
      // Payment has already committed. A read failure cannot reverse it or
      // cause the UI to submit a second charge for the same purchase.
      await Promise.allSettled([
        queryClient.invalidateQueries({ queryKey: ["browser-shop"] }),
        ...(globalId ? [
          queryClient.invalidateQueries({
            queryKey: queryKeys.account.current(globalId),
            refetchType: "active",
          }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.snapshot.current(globalId),
            refetchType: "active",
          }),
        ] : []),
      ]);
    },
  });
}
