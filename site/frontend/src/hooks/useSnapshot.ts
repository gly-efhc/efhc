import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef } from "react";
import { useRouter } from "next/router";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import { queryKeys } from "../queries/queryKeys";
import { emptyOwnerSnapshot } from "../lib/browserFallback";
import { activateUserDataOwner } from "../lib/queryClient";
import {
  fetchSyncSnapshot,
  type SyncSnapshot,
} from "../services/snapshot.service";

export type { SyncSnapshot } from "../services/snapshot.service";

export type SnapshotStatus = "idle" | "loading" | "success" | "error";
const useBeforePaintEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

export function useSnapshot() {
  const router = useRouter();
  const entry = useRef(router.pathname);
  const globalId = useAuthOwnerGlobalId();
  const client = useQueryClient();
  const admin = router.pathname === "/admin" || router.pathname.startsWith("/admin/");
  useBeforePaintEffect(() => { activateUserDataOwner(client, globalId, admin); }, [client, globalId, admin]);
  const q = useQuery({
    queryKey: queryKeys.snapshot.current(globalId),
    enabled: Boolean(globalId),
    // Persisted snapshots are an offline display fallback, not proof that
    // today's financial or energy values have been checked with the server.
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    refetchOnReconnect: "always",
    refetchInterval: globalId ? 30_000 : false,
    queryFn: async ({signal}) => {
      const result = await fetchSyncSnapshot(signal);
      if (result.profile.global_id !== globalId) throw new Error("SNAPSHOT_OWNER_MISMATCH");
      return result;
    },
  });
  useEffect(() => {
    if (entry.current === router.pathname) return;
    entry.current = router.pathname;
    if (globalId && q.data && !q.isFetching) void q.refetch();
  }, [router.pathname, globalId, q.refetch]);

  const status: SnapshotStatus = q.data
    ? "success"
    : !globalId
      ? "idle"
      : q.isError
        ? "error"
        : "loading";

  const refresh = () => {
    // The global Refresh action must also update the available-kWh preview
    // shared by Energy and Exchange, not only the lifetime snapshot.
    if (globalId) {
      void client.invalidateQueries({
        queryKey: queryKeys.exchange.preview(globalId),
        refetchType: "active",
      });
    }
    return q.refetch();
  };

  return {
    snap: q.data && q.data.profile.global_id === globalId ? q.data : globalId ? emptyOwnerSnapshot(globalId) : null,
    status,
    loading: status === "loading",
    refreshing: Boolean(q.data) && q.isFetching,
    error: q.isError,
    refresh,
    updatedAt: q.dataUpdatedAt,
  };
}
