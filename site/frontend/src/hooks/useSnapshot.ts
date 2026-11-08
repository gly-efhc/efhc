import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
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

export function useSnapshot() {
  const router = useRouter();
  const entry = useRef(router.pathname);
  const globalId = useAuthOwnerGlobalId();
  const client = useQueryClient();
  const admin = router.pathname === "/admin" || router.pathname.startsWith("/admin/");
  useEffect(() => { activateUserDataOwner(client, globalId, admin); }, [client, globalId, admin]);
  const q = useQuery({
    queryKey: queryKeys.snapshot.current(globalId),
    enabled: Boolean(globalId),
    staleTime: 30_000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
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

  return {
    snap: q.data && q.data.profile.global_id === globalId ? q.data : globalId ? emptyOwnerSnapshot(globalId) : null,
    status,
    loading: status === "loading",
    refreshing: Boolean(q.data) && q.isFetching,
    error: q.isError,
    refresh: q.refetch,
  };
}
