import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  openShopExternal,
  openVipNftExternal,
  type ShopLauncherResult,
} from "../lib/portal/shopLauncher";
import {
  createShopLauncherAccess,
  getShopLauncherTruth,
} from "../services/shopLauncher.service";

export function useShopLauncherTruth() {
  return useQuery({
    queryKey: ["shop-launcher", "truth"],
    queryFn: () => getShopLauncherTruth(),
    staleTime: 10_000,
  });
}

export function useShopLauncher() {
  const queryClient = useQueryClient();

  return useMutation<ShopLauncherResult, Error, void>({
    mutationFn: async () => {
      // Canon: the in-app Shop control is only a signed launcher.
      // Product/catalog UI belongs exclusively to the separate browser document
      // served from the same VPS at canonical /browser-shop.
      const access = await createShopLauncherAccess();
      openShopExternal(access.redirect_url);
      return "browser_shop_opened";
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["browser-shop"],
      });
    },
  });
}


export function useVipNftLauncher() {
  return useMutation<ShopLauncherResult, Error, void>({
    mutationFn: async () => {
      // OWNER CANON: second HUB link is immutable direct GetGems navigation.
      openVipNftExternal();
      return "vip_collection_opened";
    },
  });
}
