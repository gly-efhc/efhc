import { useMutation, useQuery } from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {
  openDirectDeposit,
  readDirectDepositStatus,
} from "../services/directDeposit.service";
import { queryKeys } from "./queryKeys";

export function useDirectDepositOpen() {
  return useMutation({
    mutationFn: openDirectDeposit,
  });
}

export function useDirectDepositStatus(
  openedAt: string | null,
) {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: queryKeys.directDeposit.status(globalId, openedAt),
    enabled: Boolean(globalId && openedAt),
    queryFn: ({ signal }) => readDirectDepositStatus(
      openedAt || "",
      signal,
    ),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.state === "confirmed" ? false : 4_000;
    },
    staleTime: 0,
  });
}
