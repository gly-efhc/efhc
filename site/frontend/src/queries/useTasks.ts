import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {
  claimTask,
  getMyTasks,
  getTaskEarnings,
  getTasksCatalog,
  selectTaskCatalog,
  selectMyTasks,
  selectTaskEarnings,
} from "../services/tasks.service";
import type { GlobalId } from "../types/identity";
import { queryKeys } from "./queryKeys";

async function invalidateTaskState(
  queryClient: ReturnType<typeof useQueryClient>,
  globalId: GlobalId | null,
): Promise<void> {
  // A confirmed reward is not a failed claim if any follow-up read fails.
  await Promise.allSettled([
    queryClient.invalidateQueries({
      queryKey: queryKeys.tasks.mine(globalId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.snapshot.current(globalId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.tasks.earnings(globalId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.account.current(globalId),
      refetchType: "active",
    }),
  ]);
}

export function useTasksCatalog() {
  return useQuery({
    queryKey: queryKeys.tasks.catalog,
    enabled: true,
    staleTime: 60_000,
    queryFn: getTasksCatalog,
    select: selectTaskCatalog,
  });
}

export function useTaskEarnings() {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: queryKeys.tasks.earnings(globalId),
    enabled: Boolean(globalId),
    staleTime: 10_000,
    queryFn: getTaskEarnings,
    select: selectTaskEarnings,
  });
}

export function useMyTasks() {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: queryKeys.tasks.mine(globalId),
    enabled: Boolean(globalId),
    staleTime: 10_000,
    queryFn: getMyTasks,
    select: selectMyTasks,
  });
}

export function useClaimTask() {
  const globalId = useAuthOwnerGlobalId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: claimTask,
    onSuccess: async () => {
      await invalidateTaskState(queryClient, globalId);
    },
  });
}

export function useRefreshTaskState() {
  const globalId = useAuthOwnerGlobalId();
  const queryClient = useQueryClient();
  return async (): Promise<void> => {
    await invalidateTaskState(queryClient, globalId);
  };
}
