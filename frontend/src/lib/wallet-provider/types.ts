import type { TonWalletTransaction } from "../ton/tx";
import type { DbId } from "../../types/db-id";

export type WalletAdapterId =
  | "tonconnect"
  | "telegram_wallet"
  | "native_gram_wallet";

export type WalletConnectionPhase =
  | "restoring"
  | "disconnected"
  | "proof_ready"
  | "connecting"
  | "verifying"
  | "connected"
  | "rejected"
  | "error";

export type WalletTransactionPhase =
  | "idle"
  | "signing"
  | "signed"
  | "rejected"
  | "error";

export type WalletView = {
  adapterId: WalletAdapterId;
  walletKey: string;
  name: string;
  appName: string | null;
  imageUrl: string | null;
  aboutUrl: string | null;
  universalUrl?: string | null;
  platforms?: string[];
  embedded: boolean;
  injected: boolean;
};

export type WalletSession = {
  adapterId: WalletAdapterId;
  address: string;
  providerName: string;
  raw: unknown;
};

export type PreparedWalletProof = {
  adapterId: WalletAdapterId;
  value: unknown;
};

export type WalletBindingResult = {
  wallet_id: DbId;
  wallet_address: string;
  is_connected: boolean;
};

export type WalletTransactionRequest = TonWalletTransaction;

export type WalletTransactionResult = {
  boc: string | null;
  traceId: string | null;
  provider: WalletAdapterId;
};

export type WalletAdapterSnapshot = {
  available: boolean;
  restoreSettled: boolean;
  modalOpened: boolean;
  session: WalletSession | null;
};

export type WalletAdapterDescriptor = {
  id: WalletAdapterId;
  label: string;
  available: boolean;
  connected: boolean;
};

export interface WalletAdapter {
  readonly id: WalletAdapterId;
  readonly label: string;
  getSnapshot(): WalletAdapterSnapshot;
  subscribe(listener: () => void): () => void;
  listWallets(): Promise<WalletView[]>;
  prepareProof(): Promise<PreparedWalletProof | null>;
  connect(wallet?: WalletView): Promise<void>;
  bindWallet(
    proofState: PreparedWalletProof | null,
  ): Promise<WalletBindingResult | null>;
  disconnect(): Promise<void>;
  sendTransaction(
    tx: WalletTransactionRequest,
  ): Promise<WalletTransactionResult>;
  isUserRejected(error: unknown): boolean;
}

export class WalletAdapterUnavailableError extends Error {
  readonly adapterId: WalletAdapterId;

  constructor(adapterId: WalletAdapterId) {
    super(`WALLET_ADAPTER_UNAVAILABLE:${adapterId}`);
    this.name = "WalletAdapterUnavailableError";
    this.adapterId = adapterId;
  }
}

export class WalletUserRejectedError extends Error {
  readonly adapterId: WalletAdapterId;

  constructor(adapterId: WalletAdapterId) {
    super(`WALLET_USER_REJECTED:${adapterId}`);
    this.name = "WalletUserRejectedError";
    this.adapterId = adapterId;
  }
}
