import { Address } from "@ton/core/dist/address/Address";

import type { WalletView } from "./types";

export type PrimaryWalletDescriptor = {
  wallet_address: string;
  wallet_app?: string | null;
  is_primary: boolean;
  is_active: boolean;
  proof_verified?: boolean;
};

export type PrimaryWalletExecutionReason =
  | "no_primary"
  | "primary_transport_unavailable";

export type PrimaryWalletExecutionResult<T extends PrimaryWalletDescriptor> =
  | { state: "executed"; primary: T }
  | { state: "primary_opened"; primary: T }
  | {
      state: "chooser_opened";
      primary: T | null;
      reason: PrimaryWalletExecutionReason;
    };

function normalizedWalletApp(value: string | null | undefined): string {
  const normalized = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
  if (normalized === "mytonwallet" || normalized === "mywallet") {
    return "mytonwallet";
  }
  return normalized;
}

function walletViewAliases(wallet: WalletView): string[] {
  return [wallet.walletKey, wallet.appName, wallet.name]
    .map(normalizedWalletApp)
    .filter(Boolean);
}

export function sameTonAddress(
  left: string | null | undefined,
  right: string | null | undefined,
): boolean {
  const a = String(left || "").trim();
  const b = String(right || "").trim();
  if (!a || !b) return false;
  try {
    return Address.parse(a).toRawString() === Address.parse(b).toRawString();
  } catch {
    return a.toLowerCase() === b.toLowerCase();
  }
}

export function primaryLinkedWallet<T extends PrimaryWalletDescriptor>(
  wallets: readonly T[] | null | undefined,
): T | null {
  return (wallets || []).find((wallet) => (
    wallet.is_primary
    && wallet.is_active
    && wallet.proof_verified !== false
    && Boolean(String(wallet.wallet_address || "").trim())
  )) || null;
}

/**
 * Resolve persistent wallet_app only against metadata returned by the active
 * TON Connect registry. Matching is canonical/exact after punctuation/case
 * normalization; fuzzy substring routing is intentionally forbidden because
 * it can resolve the wrong execution wallet.
 */
export function matchPrimaryWalletTransport(
  walletApp: string | null | undefined,
  availableWallets: readonly WalletView[],
): WalletView | null {
  const target = normalizedWalletApp(walletApp);
  if (!target) return null;
  return availableWallets.find((wallet) => (
    walletViewAliases(wallet).includes(target)
  )) || null;
}

export function primaryWalletSessionMatches(
  primary: PrimaryWalletDescriptor | null | undefined,
  sessionAddress: string | null | undefined,
): boolean {
  return Boolean(
    primary
    && sameTonAddress(sessionAddress, primary.wallet_address),
  );
}

export async function openPrimaryWalletSession(args: {
  primary: PrimaryWalletDescriptor;
  currentSessionAddress: string | null | undefined;
  listWallets: () => Promise<WalletView[]>;
  connectWallet: (wallet?: WalletView) => Promise<void>;
  disconnectWallet: () => Promise<void>;
}): Promise<"ready" | "opened" | "transport_unavailable"> {
  if (primaryWalletSessionMatches(args.primary, args.currentSessionAddress)) {
    return "ready";
  }
  const available = await args.listWallets().catch(() => [] as WalletView[]);
  const target = matchPrimaryWalletTransport(args.primary.wallet_app, available);
  if (!target) return "transport_unavailable";
  if (String(args.currentSessionAddress || "").trim()) {
    await args.disconnectWallet().catch(() => undefined);
  }
  // A server-verified primary wallet remains authoritative. The official
  // TON Connect modal must let the person select an app themselves; never
  // invoke the removed per-wallet custom connector. The returned wallet
  // address is independently checked against the primary before payment.
  await args.connectWallet();
  return "opened";
}

/**
 * Single orchestration entry for user financial actions that require TON
 * Connect. Persistent primary binding owns wallet choice. The SDK registry
 * chooser is opened only when there is no primary or when the primary app
 * cannot be resolved from current registry metadata.
 */
export async function routePrimaryWalletExecution<
  T extends PrimaryWalletDescriptor,
>(args: {
  wallets: readonly T[] | null | undefined;
  currentSessionAddress: string | null | undefined;
  listWallets: () => Promise<WalletView[]>;
  connectWallet: (wallet?: WalletView) => Promise<void>;
  disconnectWallet: () => Promise<void>;
  openChooser: (reason: PrimaryWalletExecutionReason) => Promise<void> | void;
  markPending: (primary: T | null) => void;
  execute: (primary: T) => Promise<void>;
}): Promise<PrimaryWalletExecutionResult<T>> {
  const primary = primaryLinkedWallet(args.wallets);
  if (!primary) {
    args.markPending(null);
    await args.openChooser("no_primary");
    return { state: "chooser_opened", primary: null, reason: "no_primary" };
  }

  if (primaryWalletSessionMatches(primary, args.currentSessionAddress)) {
    await args.execute(primary);
    return { state: "executed", primary };
  }

  args.markPending(primary);
  const route = await openPrimaryWalletSession({
    primary,
    currentSessionAddress: args.currentSessionAddress,
    listWallets: args.listWallets,
    connectWallet: args.connectWallet,
    disconnectWallet: args.disconnectWallet,
  });
  if (route === "transport_unavailable") {
    await args.openChooser("primary_transport_unavailable");
    return {
      state: "chooser_opened",
      primary,
      reason: "primary_transport_unavailable",
    };
  }
  return { state: "primary_opened", primary };
}
