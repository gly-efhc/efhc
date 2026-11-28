import { useAuthSessionController, useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {cachedAdminView} from "../lib/adminViewState";
import { useCallback, useEffect, useState } from "react";
import {
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import type {
  ApiRequestOptions,
  HttpMethod,
} from "../lib/api";
import {
  adminLinkedRequest,
  readAdminDisplay,
  type AdminLinkedRequest,
} from "../services/adminLinked.service";

export const adminLinkedKeys = {
  all: ["admin-linked"] as const,
  request: (path: string) => ["admin-linked", path] as const,
};

export function useAdminLinkedTransport() {
  const queryClient = useQueryClient();
  // Imperative Admin loaders have no active QueryObserver. Rebind their read
  // callback on the same coalesced activity signal used by subscribed pages.
  const [activityVersion, setActivityVersion] = useState(0);
  useEffect(() => {
    const refresh = () => setActivityVersion(value => value + 1);
    window.addEventListener("efhc:activity-sync", refresh);
    return () => window.removeEventListener("efhc:activity-sync", refresh);
  }, []);
  const auth = useAuthSessionController();
  const displayOwner=useAuthOwnerGlobalId();
  const cacheOwner = auth.context?.global_id ?? (cachedAdminView(displayOwner)?displayOwner:null) ?? null;
  const { mutateAsync } = useMutation({
    mutationFn: (request: AdminLinkedRequest) =>
      adminLinkedRequest<unknown>(request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        predicate: query => ["admin-linked", "syncSnapshot", "panels", "exchangePreview", "ranks", "profile", "browser-shop"].includes(String(query.queryKey[0])),
      });
    },
  });

  return useCallback(
    async function linkedRequest<T>(
      path: string,
      method: HttpMethod,
      options: ApiRequestOptions = {},
    ): Promise<T> {
      if (method === "GET") {
        return await readAdminDisplay(cacheOwner, path, () => queryClient.fetchQuery({
          queryKey: [...adminLinkedKeys.request(path), cacheOwner],
          queryFn: () => adminLinkedRequest<T>({
            path,
            method,
            options,
          }),
          staleTime: 0,
        }));
      }

      return await mutateAsync({
        path,
        method,
        options,
      }) as T;
    },
    [mutateAsync, queryClient, cacheOwner, activityVersion],
  );
}
