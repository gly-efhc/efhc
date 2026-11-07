/** Reconcile to the confirmed value immediately, including downward corrections.
 * This is display state, never a ledger write. */
export function reconcileEnergyAnchor(_previous: {base_scaled: bigint; base_client_ms: number}, confirmed: bigint, now: number) {
  return {base_scaled: confirmed < 0n ? 0n : confirmed, base_client_ms: now};
}

/** Maximum display-only projection until the next known panel expiry.
 * This never affects lifetime accounting, ledger or server-authoritative UTC.
 * An unavailable/invalid expiry is handled conservatively; absent expiry means
 * no known cutoff, and server-side verification still decides all balances. */
export function energyDisplayProjectionWindowMs(serverNowIso: string | null, nearestExpiryIso: string | null): number {
  if (!nearestExpiryIso) return Infinity;
  if (!serverNowIso) return 0;
  const start = Date.parse(serverNowIso);
  const expiry = Date.parse(nearestExpiryIso);
  if (!Number.isFinite(start) || !Number.isFinite(expiry)) return 0;
  return Math.max(0, expiry - start);
}
