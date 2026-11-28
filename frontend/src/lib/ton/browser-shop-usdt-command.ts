import type {
  BrowserShopUsdtRuntimeState,
} from "./browser-shop-usdt-runtime";

export type BrowserShopUsdtCommandSummary = {
  canPreview: boolean;
  canCheckout: boolean;
  actionLabel: string;
  warnings: string[];
};

export function getBrowserShopUsdtCommandSummary(
  state: BrowserShopUsdtRuntimeState,
): BrowserShopUsdtCommandSummary {
  const warnings = [...state.blockingReasons];

  if (state.canRunCheckout) {
    return {
      canPreview: true,
      canCheckout: true,
      actionLabel: "USDT checkout allowed",
      warnings,
    };
  }

  if (state.canBuildPreview) {
    return {
      canPreview: true,
      canCheckout: false,
      actionLabel: "USDT preview only",
      warnings,
    };
  }

  return {
    canPreview: false,
    canCheckout: false,
    actionLabel: "USDT checkout blocked",
    warnings,
  };
}
