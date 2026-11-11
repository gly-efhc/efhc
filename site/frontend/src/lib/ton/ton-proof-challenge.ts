/**
 * Browser-side preflight for a server-issued TON Proof challenge.
 * This is not proof verification; cryptographic checks remain server-owned.
 * Reject mismatched app origins before a wallet is asked to sign.
 */
export type IssuedTonProofChallenge = {
  ton_proof_payload: string;
  payload_token: string;
  expires_at: string;
  domain: string;
};

export function assertFreshTonProofChallenge(
  challenge: IssuedTonProofChallenge,
  visibleHostname: string,
  nowMs: number = Date.now(),
): void {
  const hostname = visibleHostname.toLowerCase().replace(/\.$/, "");
  if (!hostname || challenge.domain !== hostname) {
    throw new Error("TON_PROOF_DOMAIN_MISMATCH");
  }
  if (!challenge.ton_proof_payload || !challenge.payload_token) {
    throw new Error("TON_PROOF_CHALLENGE_INVALID");
  }
  const expiresAt = Date.parse(challenge.expires_at);
  if (!Number.isFinite(expiresAt) || expiresAt <= nowMs + 30_000) {
    throw new Error("TON_PROOF_CHALLENGE_EXPIRED");
  }
}
