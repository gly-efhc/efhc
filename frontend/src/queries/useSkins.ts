import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import {
  activateSkin,
  activateSwitcherSkin,
  buySkin,
  getMySkins,
  getSkinsCatalog,
  getSkinSwitcher,
} from "../services/skins.service";

const skinKeys = {
  all: ["skins"] as const,
  catalog: ["skins", "catalog"] as const,
  mine: (globalId: string | null) => [
    "skins",
    "mine",
    globalId,
  ] as const,
  switcher: (globalId: string | null) => [
    "skins",
    "switcher",
    globalId,
  ] as const,
};

function dispatchSkinChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("efhc_shop_skin_changed"));
  }
}

export function useMySkins() {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: skinKeys.mine(globalId),
    enabled: Boolean(globalId),
    queryFn: getMySkins,
    staleTime: 10_000,
  });
}

export function useSkinsCatalog() {
  return useQuery({
    queryKey: skinKeys.catalog,
    queryFn: getSkinsCatalog,
    staleTime: 30_000,
  });
}

export function useSkinSwitcher() {
  const globalId = useAuthOwnerGlobalId();
  return useQuery({
    queryKey: skinKeys.switcher(globalId),
    enabled: Boolean(globalId),
    queryFn: getSkinSwitcher,
    staleTime: 10_000,
  });
}

export function useSkinActions() {
  const queryClient = useQueryClient();
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: skinKeys.all });
    dispatchSkinChanged();
  };
  const buy = useMutation({
    mutationFn: buySkin,
    onSuccess: invalidate,
  });
  const activate = useMutation({
    mutationFn: activateSkin,
    onSuccess: invalidate,
  });
  const activateSwitcher = useMutation({
    mutationFn: activateSwitcherSkin,
    onSuccess: invalidate,
  });
  return { buy, activate, activateSwitcher };
}
