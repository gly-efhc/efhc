import {
  WalletAdapterUnavailableError,
  WalletUserRejectedError,
  type PreparedWalletProof,
  type WalletAdapter,
  type WalletAdapterId,
  type WalletAdapterSnapshot,
  type WalletBindingResult,
  type WalletSession,
  type WalletTransactionRequest,
  type WalletTransactionResult,
  type WalletView,
} from "../types";

/**
 * Stable EFHC bridge for wallet APIs that are not published yet.
 * official Telegram/GRAM API is mapped inside its adapter only
 * pages never depend on the external API shape directly.
 */
export interface EfhcWalletAdapterBridgeV1 {
  readonly version: "1";
  getSnapshot(): Partial<WalletAdapterSnapshot>;
  subscribe?(listener: () => void): () => void;
  listWallets?(): Promise<WalletView[]>;
  prepareProof?(): Promise<unknown | null>;
  connect(): Promise<WalletSession | void>;
  bindWallet?(args: {
    proofState: unknown | null;
    session: WalletSession | null;
  }): Promise<WalletBindingResult | null>;
  disconnect(): Promise<void>;
  sendTransaction(tx: WalletTransactionRequest): Promise<{
    boc?: string | null;
    traceId?: string | null;
  }>;
  isUserRejected?(error: unknown): boolean;
}

type BridgeResolver = () => EfhcWalletAdapterBridgeV1 | null;

function emptySnapshot(): WalletAdapterSnapshot {
  return {
    available: false,
    restoreSettled: true,
    modalOpened: false,
    session: null,
  };
}

function normalizedSession(
  adapterId: WalletAdapterId,
  session: WalletSession | null | undefined,
): WalletSession | null {
  if (typeof session?.address !== "string" || !session.address.trim()) return null;
  return {
    adapterId,
    address: String(session.address),
    providerName: String(session.providerName || adapterId),
    raw: session.raw ?? null,
  };
}

function resolveOrThrow(
  adapterId: WalletAdapterId,
  resolver: BridgeResolver,
): EfhcWalletAdapterBridgeV1 {
  const bridge = resolver();
  if (!bridge || bridge.version !== "1") {
    throw new WalletAdapterUnavailableError(adapterId);
  }
  try {
    const current = bridge.getSnapshot();
    if (
      (current.available !== undefined && current.available !== true)
      || typeof bridge.connect !== "function"
      || typeof bridge.disconnect !== "function"
      || typeof bridge.sendTransaction !== "function"
    ) throw new WalletAdapterUnavailableError(adapterId);
  } catch {
    throw new WalletAdapterUnavailableError(adapterId);
  }
  return bridge;
}

function genericUserRejected(error: unknown): boolean {
  const record = error as {
    code?: string | number;
    name?: string;
    message?: string;
  } | null;
  const text = [record?.code, record?.name, record?.message]
    .map((item) => String(item ?? "").toUpperCase())
    .join(" ");
  return text.includes("USER_REJECT")
    || text.includes("USER DECLINED")
    || text.includes("USER CANCELLED")
    || text.includes("USER CANCELED");
}

export function createBridgeWalletAdapter(args: {
  id: WalletAdapterId;
  label: string;
  resolveBridge: BridgeResolver;
}): WalletAdapter {
  const snapshot = (): WalletAdapterSnapshot => {
    const bridge = args.resolveBridge();
    if (!bridge || bridge.version !== "1") return emptySnapshot();
    try {
      const current = bridge.getSnapshot();
      if (
        (current.available !== undefined && typeof current.available !== "boolean")
        || typeof bridge.connect !== "function"
        || typeof bridge.disconnect !== "function"
        || typeof bridge.sendTransaction !== "function"
      ) return emptySnapshot();
      return {
        available: current.available !== false,
        restoreSettled: current.restoreSettled !== false,
        modalOpened: Boolean(current.modalOpened),
        session: current.available === false
          ? null : normalizedSession(args.id, current.session),
      };
    } catch {
      return emptySnapshot();
    }
  };

  return {
    id: args.id,
    label: args.label,
    getSnapshot: snapshot,
    subscribe(listener) {
      let subscribedBridge: EfhcWalletAdapterBridgeV1 | null = null;
      let unsubscribeBridge: () => void = () => undefined;
      const attachBridge = () => {
        const resolved = args.resolveBridge();
        const bridge = resolved?.version === "1" ? resolved : null;
        if (bridge === subscribedBridge) return;
        try { unsubscribeBridge(); } catch { /* provider cleanup is best effort */ }
        subscribedBridge = bridge;
        unsubscribeBridge = () => undefined;
        try {
          const unsubscribe = bridge?.subscribe?.(listener);
          if (typeof unsubscribe === "function") unsubscribeBridge = unsubscribe;
        } catch {
          // Installation/status events still provide safe availability updates.
        }
      };
      const onBridgeEvent = () => {
        attachBridge();
        listener();
      };
      attachBridge();
      const eventName = `efhc:wallet-adapter:${args.id}`;
      if (typeof window !== "undefined") {
        window.addEventListener(eventName, onBridgeEvent);
      }
      return () => {
        try { unsubscribeBridge(); } catch { /* provider cleanup is best effort */ }
        if (typeof window !== "undefined") {
          window.removeEventListener(eventName, onBridgeEvent);
        }
      };
    },
    async listWallets() {
      const bridge = resolveOrThrow(args.id, args.resolveBridge);
      const wallets = bridge.listWallets
        ? await bridge.listWallets()
        : [];
      return wallets.map((wallet) => ({
        ...wallet,
        walletKey: String(
          wallet.walletKey || wallet.appName || wallet.name || args.id,
        ),
        adapterId: args.id,
      }));
    },
    async prepareProof() {
      const bridge = resolveOrThrow(args.id, args.resolveBridge);
      if (!bridge.prepareProof) return null;
      const value = await bridge.prepareProof();
      return value === null || value === undefined
        ? null
        : { adapterId: args.id, value };
    },
    async connect() {
      const bridge = resolveOrThrow(args.id, args.resolveBridge);
      await bridge.connect();
    },
    async bindWallet(proofState: PreparedWalletProof | null) {
      const bridge = resolveOrThrow(args.id, args.resolveBridge);
      if (!bridge.bindWallet) return null;
      if (proofState && proofState.adapterId !== args.id) return null;
      return await bridge.bindWallet({
        proofState: proofState?.value ?? null,
        session: snapshot().session,
      });
    },
    async disconnect() {
      const bridge = resolveOrThrow(args.id, args.resolveBridge);
      await bridge.disconnect();
    },
    async sendTransaction(
      tx: WalletTransactionRequest,
    ): Promise<WalletTransactionResult> {
      const bridge = resolveOrThrow(args.id, args.resolveBridge);
      try {
        const out = await bridge.sendTransaction(tx);
        if (
          !out || typeof out !== "object"
          || (out.boc != null && typeof out.boc !== "string")
          || (out.traceId != null && typeof out.traceId !== "string")
        ) throw new Error("WALLET_TRANSACTION_RESPONSE_INVALID");
        return {
          boc: typeof out?.boc === "string" ? out.boc : null,
          traceId:
            typeof out?.traceId === "string" ? out.traceId : null,
          provider: args.id,
        };
      } catch (error) {
        if (
          bridge.isUserRejected?.(error)
          || genericUserRejected(error)
        ) {
          throw new WalletUserRejectedError(args.id);
        }
        throw error;
      }
    },
    isUserRejected(error: unknown) {
      const bridge = args.resolveBridge();
      return error instanceof WalletUserRejectedError
        || Boolean(bridge?.isUserRejected?.(error))
        || genericUserRejected(error);
    },
  };
}
