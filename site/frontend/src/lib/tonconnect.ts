import type { Lang } from "./i18n";
import {
  requireGenesisTransactionNetwork,
  requireGenesisWalletNetwork,
} from "./ton/testnet-guard";
import {
  checkTonProofEnvelope,
  connectVerifiedTonWallet,
  getTonProofPayload,
  type TonProofPayloadResponse,
} from "../services/tonConnect.service";
import type { DbId } from "../types/db-id";

export type TonConnectWalletView = {
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

export type PreparedTonProof = TonProofPayloadResponse;

export type TonConnectConnectionPhase =
  | "restoring"
  | "disconnected"
  | "proof_ready"
  | "connecting"
  | "verifying"
  | "connected"
  | "rejected"
  | "error";

export type TonConnectTransactionPhase =
  | "idle"
  | "signing"
  | "signed"
  | "rejected"
  | "error";

export class TonConnectUserRejectedError extends Error {
  constructor() {
    super("TONCONNECT_USER_REJECTED");
    this.name = "TonConnectUserRejectedError";
  }
}

export function tonConnectLanguage(lang: Lang): string {
  if (lang === "ru") return "ru";
  if (lang === "uk") return "uk";
  if (lang === "tr") return "tr";
  if (lang === "de") return "de";
  if (lang === "fr") return "fr";
  if (lang === "es") return "es";
  return "en";
}

export function tonConnectTheme(
  themeMode: "auto" | "dark" | "light",
  tgScheme: "light" | "dark" | null = null,
): string {
  if (themeMode === "dark") return "DARK";
  if (themeMode === "light") return "LIGHT";
  if (tgScheme === "light") return "LIGHT";
  return "DARK";
}

export async function prepareTonProof(
  tonConnectUI: any,
): Promise<PreparedTonProof | null> {
  if (!tonConnectUI?.setConnectRequestParameters) return null;
  tonConnectUI.setConnectRequestParameters({ state: "loading" });
  try {
    const out = await getTonProofPayload();
    tonConnectUI.setConnectRequestParameters({
      state: "ready",
      value: { tonProof: out.ton_proof_payload },
    });
    return out;
  } catch {
    tonConnectUI.setConnectRequestParameters(null);
    return null;
  }
}

function proofEnvelope(
  wallet: any,
  proofState: PreparedTonProof | null,
): Record<string, unknown> | null {
  const proof = wallet?.connectItems?.tonProof?.proof;
  const address = String(wallet?.account?.address || "").trim();
  if (!proofState || !proof || !address) return null;
  requireGenesisWalletNetwork(wallet?.account?.chain);
  return {
    address,
    wallet_app: walletTransportAppName(wallet),
    payload_token: proofState.payload_token,
    public_key: wallet?.account?.publicKey || null,
    network: wallet?.account?.chain || null,
    proof: {
      timestamp: Number(proof.timestamp || 0),
      domain: proof.domain,
      signature: String(proof.signature || ""),
      payload: String(proof.payload || ""),
      state_init: wallet?.account?.walletStateInit || null,
    },
  };
}

function boundedWalletDisplayName(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  return value.trim().slice(0, 64);
}

function walletTransportAppName(wallet: any): string | null {
  const value = [wallet?.device?.appName, wallet?.appName].find(
    (item) => typeof item === "string" && item.trim().length > 0,
  );
  if (typeof value !== "string") return null;
  const appName = value.trim().slice(0, 64);
  const normalized = appName.toLowerCase().replace(/[^a-z0-9]+/g, "");
  // Upstream technical ID remains mytonwallet; legacy aliases normalize to it.
  if (normalized === "mywallet" || normalized === "mytonwallet") return "mytonwallet";
  return appName;
}

function newIdempotencyKey(prefix: string): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return `${prefix}:${uuid}`;
  const random = Math.random().toString(16).slice(2);
  return `${prefix}:${Date.now()}:${random}`;
}

export async function submitTonProofEnvelope(
  wallet: any,
  proofState: PreparedTonProof | null,
): Promise<{
  accepted: boolean;
  cryptographically_verified: boolean;
} | null> {
  const body = proofEnvelope(wallet, proofState);
  if (!body) return null;
  const {
    wallet_app: _walletApp,
    ...proofOnlyBody
  } = body;
  return await checkTonProofEnvelope(proofOnlyBody);
}

export async function bindVerifiedTonConnectWallet(
  wallet: any,
  proofState: PreparedTonProof | null,
): Promise<{
  wallet_id: DbId;
  wallet_address: string;
  is_connected: boolean;
} | null> {
  const body = proofEnvelope(wallet, proofState);
  if (!body) return null;
  return await connectVerifiedTonWallet({
    idempotencyKey: newIdempotencyKey("tonconnect-bind"),
    body,
  });
}

export async function bindTonConnectWallet(
  wallet: any,
  proofState?: PreparedTonProof | null,
) {
  return await bindVerifiedTonConnectWallet(
    wallet,
    proofState || null,
  );
}

export async function fetchTonConnectWallets(
  tonConnectUI: any,
): Promise<TonConnectWalletView[]> {
  const e2eDisabled =
    process.env.NEXT_PUBLIC_EFHC_E2E_DISABLE_TONCONNECT_RESTORE === "1"
    && process.env.NEXT_PUBLIC_EFHC_PAGES_PREVIEW !== "1";
  if (e2eDisabled) return [];
  if (!tonConnectUI?.getWallets) return [];
  const raw = await tonConnectUI.getWallets();
  const items = Array.isArray(raw) ? raw : [];
  return items
    .map((item: any) => ({
      walletKey: String(item?.appName || item?.name || "TON wallet").trim(),
      name: boundedWalletDisplayName(item?.name || item?.appName)
        || "TON wallet",
      appName: item?.appName ? String(item.appName) : null,
      imageUrl: item?.imageUrl ? String(item.imageUrl) : null,
      aboutUrl: item?.aboutUrl ? String(item.aboutUrl) : null,
      universalUrl: item?.universalLink ? String(item.universalLink) : null,
      platforms: Array.isArray(item?.platforms) ? item.platforms.map((value: unknown) => String(value)) : [],
      embedded: Boolean(item?.embedded),
      injected: Boolean(item?.injected),
    }))
    .sort((a, b) => {
      const rank = (w: TonConnectWalletView): number =>
        w.embedded ? 0 : w.injected ? 1 : 2;
      return rank(a) - rank(b) || a.name.localeCompare(b.name);
    });
}

export async function waitTonConnectRestore(
  tonConnectUI: any,
): Promise<boolean> {
  try {
    if (tonConnectUI?.connectionRestored?.then) {
      return Boolean(await tonConnectUI.connectionRestored);
    }
  } catch {
    return false;
  }
  return false;
}

export function isTonConnectUserRejected(error: unknown): boolean {
  const value = error as {
    code?: number | string;
    name?: string;
    message?: string;
  } | null;
  const code = String(value?.code ?? "").toUpperCase();
  const name = String(value?.name ?? "").toUpperCase();
  const message = String(value?.message ?? "").toUpperCase();
  return code === "300"
    || name === "USERREJECTSERROR"
    || name.includes("USER_REJECT")
    || message.includes("USER_REJECT")
    || message.includes("USER DECLINED")
    || message.includes("USER REJECTED");
}

export async function sendTonConnectTransaction(
  tonConnectUI: any,
  tx: unknown,
): Promise<{ boc: string | null; traceId: string | null }> {
  try {
    const request = tx as { network?: unknown } | null;
    requireGenesisTransactionNetwork(
      request?.network, tonConnectUI?.wallet?.account?.chain,
    );
    const out = await tonConnectUI.sendTransaction(tx as any);
    // The SDK SendTransactionResponse requires a signed BOC. A malformed
    // fulfilled RPC response is not a successful wallet-sign acknowledgement.
    if (!out || typeof out.boc !== "string" || !out.boc.trim()) {
      throw new Error("TONCONNECT_TRANSACTION_RESPONSE_INVALID");
    }
    const record = (out || {}) as Record<string, unknown>;
    return {
      boc: typeof record.boc === "string" ? record.boc : null,
      traceId: typeof record.traceId === "string"
        ? record.traceId
        : null,
    };
  } catch (error) {
    if (isTonConnectUserRejected(error)) {
      throw new TonConnectUserRejectedError();
    }
    throw error;
  }
}

export async function disconnectTonConnect(
  tonConnectUI: any,
): Promise<void> {
  if (!tonConnectUI?.disconnect) return;
  await tonConnectUI.disconnect();
}
