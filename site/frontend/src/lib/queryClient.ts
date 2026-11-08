import { QueryClient } from "@tanstack/react-query";
import { activateUserCache, startUserDataPersistence } from "./userDataCache";
import { bindWindowSettings, resetSettings, saveSettings } from "./settings";
import {resetWindowDrafts} from "./ownerDrafts";

import {
  hydratePublicCatalogQueries,
  startPublicCatalogPersistence,
} from "./publicCatalogPersistence";

// EFHC Mini App: a single global QueryClient.
// Defaults are tuned for Telegram Mini App UX:
// - keep data "fresh enough" without hammering backend
// - refetch on focus (when user returns to Telegram)
export function createEfhcQueryClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        // Mini App: не дергаем API при каждом переходе по вкладкам.
        staleTime: 10_000,
        gcTime: 86_400_000,
        networkMode: "always",
        retry: 1,
        // Keep a restored display snapshot visible, but always refresh
        // active page data in the background on entry/focus/reconnect.
        refetchOnMount: "always",
        refetchOnWindowFocus: "always",
        refetchOnReconnect: "always",
      },
      mutations: {
        retry: 0,
        // Never queue a backend action for automatic replay when connectivity returns.
        networkMode: "always",
      },
    },
  });
  if (typeof window !== "undefined") {
    // Hydrate only after React mount in the owner-bound query hooks; pre-hydrating
    // would mismatch the statically exported SSR tree on a cached reload.
    startUserDataPersistence(client);
  }
  return client;
}

/** Hydrate public catalog after React hydration: cached FAQ must not alter
 * the first client tree relative to the static SSR markup. */
export function restorePublicCatalogAfterMount(client: QueryClient): () => void {
  if (typeof window === "undefined") return () => undefined;
  hydratePublicCatalogQueries(client);
  return startPublicCatalogPersistence(client);
}

export function activateUserDataOwner(client: QueryClient, owner: string | null, admin: boolean): boolean {
  const changed = activateUserCache(client, owner, admin);
  if (changed) {
    resetWindowDrafts(owner!);
    saveSettings(resetSettings());
    if (typeof window !== "undefined") window.dispatchEvent?.(new Event("efhc:user-owner-changed"));
  } else if (!admin && owner && bindWindowSettings()) {
    if (typeof window !== "undefined") window.dispatchEvent?.(new Event("efhc:user-settings-ready"));
  }
  return changed;
}
