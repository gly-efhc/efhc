import {
  bindVerifiedTonConnectWallet,
  disconnectTonConnect,
  fetchTonConnectWallets,
  isTonConnectUserRejected,
  prepareTonProof,
  sendTonConnectTransaction,
  TonConnectUserRejectedError,
  type PreparedTonProof,
} from "../../tonconnect";
import { isGenesisTestRuntime, TON_TESTNET_CHAIN } from "../../ton/testnet-guard";
import {
  WalletAdapterUnavailableError,
  WalletUserRejectedError,
  type PreparedWalletProof,
  type WalletAdapter,
  type WalletSession,
  type WalletTransactionRequest,
} from "../types";

function providerName(wallet: any): string {
  const value = [
    wallet?.device?.appName,
    wallet?.appName,
    wallet?.name,
    wallet?.device?.platform,
  ].find((item) => typeof item === "string" && item.trim());
  return value
    ? String(value).trim().toLowerCase()
    : "tonconnect-wallet";
}

export function createTonConnectAdapter(args: {
  tonConnectUI: any;
  wallet: any;
  address: string;
  restoreSettled: boolean;
  modalOpened: boolean;
}): WalletAdapter {
  const session = (): WalletSession | null => {
    const address = String(
      args.address || args.wallet?.account?.address || "",
    ).trim();
    if (!args.wallet || !address) return null;
    return {
      adapterId: "tonconnect",
      address,
      providerName: providerName(args.wallet),
      raw: args.wallet,
    };
  };

  const requireUi = () => {
    if (!args.tonConnectUI) {
      throw new WalletAdapterUnavailableError("tonconnect");
    }
    return args.tonConnectUI;
  };

  return {
    id: "tonconnect",
    label: "TON Connect",
    getSnapshot() {
      return {
        available: Boolean(args.tonConnectUI),
        restoreSettled: args.restoreSettled,
        modalOpened: args.modalOpened,
        session: session(),
      };
    },
    subscribe() {
      // @tonconnect/ui-react hooks provide reactive updates.
      return () => undefined;
    },
    async listWallets() {
      const ui = requireUi();
      const wallets = await fetchTonConnectWallets(ui);
      return wallets.map((wallet) => ({
        ...wallet,
        adapterId: "tonconnect" as const,
      }));
    },
    async prepareProof(): Promise<PreparedWalletProof | null> {
      const ui = requireUi();
      const proof = await prepareTonProof(ui);
      return proof
        ? { adapterId: "tonconnect", value: proof }
        : null;
    },
    async connect(wallet) {
      const ui = requireUi();
      // The official modal owns wallet selection; a previously selected
      // legacy wallet key must never invoke a hidden custom connector.
      if (wallet) throw new Error("TONCONNECT_USE_OFFICIAL_WALLET_MODAL");
      if (isGenesisTestRuntime()) {
        if (typeof ui.setConnectionNetwork !== "function") {
          throw new Error("TON_TESTNET_NETWORK_GUARD_UNAVAILABLE");
        }
        // The official SDK rejects a different chain during connect.
        // This must happen before opening the modal, not after signing.
        if (!args.wallet) ui.setConnectionNetwork(TON_TESTNET_CHAIN);
        if (args.wallet?.account?.chain !== undefined
            && args.wallet.account.chain !== TON_TESTNET_CHAIN) {
          throw new Error("TON_TESTNET_WALLET_REQUIRED");
        }
      }
      if (typeof ui.openModal !== "function") {
        throw new Error("TONCONNECT_OFFICIAL_MODAL_UNAVAILABLE");
      }
      await ui.openModal();
    },
    async bindWallet(proofState: PreparedWalletProof | null) {
      // A binding is authoritative only after a verified server TonProof.
      const current = session();
      if (
        !current
        || proofState?.adapterId !== "tonconnect"
      ) {
        return null;
      }
      return await bindVerifiedTonConnectWallet(
        current.raw,
        proofState.value as PreparedTonProof,
      );
    },
    async disconnect() {
      await disconnectTonConnect(requireUi());
    },
    async sendTransaction(tx: WalletTransactionRequest) {
      // User-confirmed transactions use the actual wallet transport and the
      // existing upstream business-contract checks; no Pages blanket block.
      try {
        const out = await sendTonConnectTransaction(requireUi(), tx, args.wallet);
        return { ...out, provider: "tonconnect" as const };
      } catch (error) {
        if (
          error instanceof TonConnectUserRejectedError
          || isTonConnectUserRejected(error)
        ) {
          throw new WalletUserRejectedError("tonconnect");
        }
        throw error;
      }
    },
    isUserRejected(error: unknown) {
      return error instanceof WalletUserRejectedError
        || error instanceof TonConnectUserRejectedError
        || isTonConnectUserRejected(error);
    },
  };
}
