import type {
  HubShopTruthResponse,
} from "../api/generated/economicUserSeams";

export const GETGEMS_EFHC_VIP_NFT_URL = "https://getgems.io/efhc-nft" as const;

// OWNER CANON: Telegram WebApp must leave Telegram for commerce; ordinary Web EFHC
// navigates to the same external Shop document in the current browser context.
export function openShopExternal(url: string) {
  if (typeof window === "undefined") return;
  const tg = (globalThis as any)?.Telegram?.WebApp;
  if (typeof tg?.openLink === "function") {
    tg.openLink(url);
    return;
  }
  window.location.assign(url);
}

// OWNER CANON: HUB VIP NFT always opens the official GetGems collection directly.
// No signed handoff, EFHC intermediate route, or Shop checkout may replace this link.
export function openVipNftExternal() {
  if (typeof window === "undefined") return;
  const tg = (globalThis as any)?.Telegram?.WebApp;
  if (typeof tg?.openLink === "function") {
    tg.openLink(GETGEMS_EFHC_VIP_NFT_URL);
    return;
  }
  window.open(GETGEMS_EFHC_VIP_NFT_URL, "_blank", "noopener,noreferrer");
}

export type ShopLauncherResult =
  | "wallet_sync_required"
  | "telegram_handoff_required"
  | "external_flow_unavailable"
  | "browser_shop_opened"
  | "vip_collection_opened";

export function getShopLauncherResult(
  truth: HubShopTruthResponse,
): ShopLauncherResult {
  const flow = truth.flow_truth;
  const primaryCta = String(flow?.primary_cta || "").trim();
  if (primaryCta === "sync_wallet") {
    return "wallet_sync_required";
  }
  if (primaryCta === "open_telegram_handoff") {
    return "telegram_handoff_required";
  }
  if (flow?.action_denied || primaryCta === "unavailable") {
    return "external_flow_unavailable";
  }
  return "browser_shop_opened";
}
