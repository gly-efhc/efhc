import type { GlobalId } from "../types/identity";
import type { DbId } from "../types/db-id";

type Owner = GlobalId | null;

export const queryKeys = {
  auth: {
    session: ["auth", "session"] as const,
    owner: (globalId: GlobalId) => [
      "auth",
      "owner",
      globalId,
    ] as const,
    provider: (globalId: GlobalId) => [
      "auth",
      "provider",
      globalId,
    ] as const,
  },
  owner: {
    resource: (globalId: GlobalId, resource: string) => [
      "owner",
      globalId,
      resource,
    ] as const,
  },
  publicStatic: {
    faq: (lang: string) => [
      "public-static",
      "faq",
      lang,
    ] as const,
  },
  snapshot: {
    current: (globalId: Owner) => [
      "syncSnapshot",
      globalId,
    ] as const,
  },
  account: {
    current: (globalId: Owner) => ["accountBalance", globalId] as const,
  },
  hub: {
    handoff: ["hub", "efhc-handoff"] as const,
  },
  directDeposit: {
    status: (
      globalId: Owner,
      openedAt: string | null,
    ) => [
      "direct-deposit",
      globalId,
      openedAt || "idle",
    ] as const,
  },
  browserShop: {
    bootstrap: (token: string) => [
      "browser-shop",
      "bootstrap",
      token,
    ] as const,
    catalog: ["browser-shop", "catalog"] as const,
    profile: (token: string) => [
      "browser-shop",
      "profile",
      token,
    ] as const,
    intentStatus: (token: string, intentId: DbId | null) => [
      "browser-shop",
      "intent-status",
      token,
      intentId,
    ] as const,
  },
  exchange: {
    preview: (globalId: Owner) => [
      "exchangePreview",
      globalId,
    ] as const,
  },
  profile: {
    wallets: (globalId: Owner) => [
      "wallets_me",
      globalId,
    ] as const,
    balanceHistory: (globalId: Owner) => [
      "profile",
      globalId,
      "balance-history",
    ] as const,
    withdrawHistory: (globalId: Owner) => [
      "profile",
      globalId,
      "withdraw-history",
    ] as const,
    exchangeHistory: (globalId: Owner) => [
      "profile",
      globalId,
      "exchange-history",
    ] as const,
  },
  panels: {
    all: (globalId: Owner) => ["panels", globalId] as const,
    summary: (globalId: Owner) => [
      "panels",
      globalId,
      "summary",
    ] as const,
    list: (
      globalId: Owner,
      tab: "active" | "archive",
    ) => ["panels", globalId, "list", tab] as const,
  },
  referrals: {
    stats: (globalId: Owner) => [
      "referrals",
      globalId,
      "stats",
    ] as const,
    list: (
      globalId: Owner,
      tab: "active" | "inactive",
    ) => ["referrals", globalId, "list", tab] as const,
  },
  ranks: {
    myPlusTop: (globalId: Owner) => [
      "ranks",
      globalId,
      "my-plus-top",
    ] as const,
    top: (globalId: Owner) => [
      "ranks",
      globalId,
      "top",
    ] as const,
  },
  tasks: {
    catalog: ["tasksCatalog"] as const,
    mine: (globalId: Owner) => ["tasksMy", globalId] as const,
    earnings: (globalId: Owner) => ["tasksEarnings", globalId] as const,
  },
  withdrawals: {
    all: (globalId: Owner) => ["withdrawals", globalId] as const,
    list: (
      globalId: Owner,
      statusFilter: string,
    ) => [
      "withdrawals",
      globalId,
      "list",
      statusFilter,
    ] as const,
    detail: (requestId: DbId | null) => [
      "withdrawal",
      requestId,
    ] as const,
    history: (globalId: Owner) => [
      "withdrawals",
      globalId,
      "balance-history",
    ] as const,
    outcome: (requestId: DbId | null) => [
      "withdrawal",
      "outcome",
      requestId,
    ] as const,
  },
} as const;
