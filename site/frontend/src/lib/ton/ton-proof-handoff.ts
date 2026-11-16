import { assertFreshTonProofChallenge } from "./ton-proof-challenge";
import type { PreparedWalletProof } from "../wallet-provider/types";

/**
 * Ephemeral TON Proof handshake across Android wallet app switches.
 *
 * The wallet transport may restore after the browser WebView was recreated.
 * Persist ONLY the previously issued public challenge and its server-bound
 * proof token in the same tab's sessionStorage; never store a wallet signature,
 * signed transaction, session JWT, private key or cross-owner binding.
 * Backend cryptographic verification remains authoritative.
 */
const KEY = "efhc.tonconnect.pending-proof.v1";

type HandoffRecord = {
  v: 1;
  ownerGlobalId: string;
  hostname: string;
  proof: PreparedWalletProof;
};

export type HandoffStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function browserTonProofStorage(): HandoffStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function clearPendingTonProof(storage: HandoffStorage | null): void {
  try {
    storage?.removeItem(KEY);
  } catch {
    // Storage may be blocked in privacy mode; never block TON Connect itself.
  }
}

function validOwner(value: string): boolean {
  return /^\\d{10}$/.test(value) && value !== "0000000000";
}

function isValidProof(value: unknown, hostname: string): value is PreparedWalletProof {
  if (!value || typeof value !== "object") return false;
  const proof = value as PreparedWalletProof;
  if (proof.adapterId !== "tonconnect" || !proof.value || typeof proof.value !== "object") return false;
  const challenge = proof.value as {
    domain?: string;
    expires_at?: string;
    ton_proof_payload?: string;
    payload_token?: string;
  };
  if (typeof challenge.domain !== "string"
    || typeof challenge.expires_at !== "string"
    || typeof challenge.ton_proof_payload !== "string"
    || typeof challenge.payload_token !== "string") return false;
  try {
    assertFreshTonProofChallenge(
      {
        domain: challenge.domain,
        expires_at: challenge.expires_at,
        ton_proof_payload: challenge.ton_proof_payload,
        payload_token: challenge.payload_token,
      },
      hostname,
    );
    return true;
  } catch {
    return false;
  }
}

export function savePendingTonProof(
  storage: HandoffStorage | null,
  ownerGlobalId: string,
  hostname: string,
  proof: PreparedWalletProof | null,
): void {
  clearPendingTonProof(storage);
  if (!storage || !validOwner(ownerGlobalId) || !isValidProof(proof, hostname)) return;
  const record: HandoffRecord = { v: 1, ownerGlobalId, hostname, proof };
  try {
    storage.setItem(KEY, JSON.stringify(record));
  } catch {
    // Connection must still work if sessionStorage is unavailable.
  }
}

export function loadPendingTonProof(
  storage: HandoffStorage | null,
  ownerGlobalId: string,
  hostname: string,
): PreparedWalletProof | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(KEY);
    if (!raw) return null;
    const record = JSON.parse(raw) as HandoffRecord;
    if (record?.v === 1
      && validOwner(ownerGlobalId)
      && record.ownerGlobalId === ownerGlobalId
      && record.hostname === hostname
      && isValidProof(record.proof, hostname)) {
      return record.proof;
    }
  } catch {
    // Malformed or unavailable storage must not create an authenticated wallet.
  }
  clearPendingTonProof(storage);
  return null;
}
