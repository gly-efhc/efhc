import { UI_COPY_KEYS, type UiCopyKey } from "./uiKeys";

export type UiCopyReplacement = {
  key: UiCopyKey;
  fallbackEn: string;
  category:
    | "wallet_finance"
    | "common_actions"
    | "system_errors"
    | "navigation_empty"
    | "bonus_social";
};

export const UI_COPY_REPLACEMENTS: Record<string, UiCopyReplacement> = {
  "Wallet connected": {
    key: UI_COPY_KEYS.walletConnected,
    fallbackEn: "Wallet connected",
    category: "wallet_finance",
  },
  "Not connected": {
    key: UI_COPY_KEYS.walletNotConnected,
    fallbackEn: "Not connected",
    category: "wallet_finance",
  },
  "Wallet required": {
    key: UI_COPY_KEYS.walletRequired,
    fallbackEn: "Wallet required",
    category: "wallet_finance",
  },
  "Purchase failed": {
    key: UI_COPY_KEYS.purchaseFailed,
    fallbackEn: "Purchase failed",
    category: "wallet_finance",
  },
  Confirm: {
    key: UI_COPY_KEYS.confirm,
    fallbackEn: "Confirm",
    category: "common_actions",
  },
  Cancel: {
    key: UI_COPY_KEYS.cancel,
    fallbackEn: "Cancel",
    category: "common_actions",
  },
  Retry: {
    key: UI_COPY_KEYS.retry,
    fallbackEn: "Retry",
    category: "common_actions",
  },
  Refresh: {
    key: UI_COPY_KEYS.refresh,
    fallbackEn: "Refresh",
    category: "common_actions",
  },
  "Something went wrong": {
    key: UI_COPY_KEYS.unexpectedError,
    fallbackEn: "Something went wrong",
    category: "system_errors",
  },
  "Access denied": {
    key: UI_COPY_KEYS.accessDenied,
    fallbackEn: "Access denied",
    category: "system_errors",
  },
  "Session expired": {
    key: UI_COPY_KEYS.sessionExpired,
    fallbackEn: "Session expired",
    category: "system_errors",
  },
  "No data found": {
    key: UI_COPY_KEYS.noDataFound,
    fallbackEn: "No data found",
    category: "navigation_empty",
  },
  Loading: {
    key: UI_COPY_KEYS.loading,
    fallbackEn: "Loading",
    category: "navigation_empty",
  },
  "Task bonus": {
    key: UI_COPY_KEYS.taskBonus,
    fallbackEn: "Task bonus",
    category: "bonus_social",
  },
  "Referral bonus": {
    key: UI_COPY_KEYS.referralBonus,
    fallbackEn: "Referral bonus",
    category: "bonus_social",
  },
  "Shop purchase": {
    key: UI_COPY_KEYS.shopPurchase,
    fallbackEn: "Shop purchase",
    category: "bonus_social",
  },
  "Panel purchase": {
    key: UI_COPY_KEYS.panelPurchase,
    fallbackEn: "Panel purchase",
    category: "bonus_social",
  },
};
