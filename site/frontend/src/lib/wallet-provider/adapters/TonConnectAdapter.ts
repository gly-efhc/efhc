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
      if (!wallet?.walletKey || typeof ui.connectWallet !== "function") {
        throw new Error("TONCONNECT_WALLET_SELECTION_REQUIRED");
      }
      await ui.connectWallet(wallet.walletKey);
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
