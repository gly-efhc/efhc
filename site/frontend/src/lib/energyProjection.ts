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


/** Elapsed wall time since the server's authoritative snapshot boundary.
 * Query updatedAt survives offline reload; it guards against a device clock
 * that was already skewed when the snapshot was received. These values are
 * display estimates only: the backend alone commits generated energy. */
export function energyElapsedSinceSnapshotMs(
  serverNowIso: string | null,
  snapshotUpdatedAtMs: number | null | undefined,
  clientNowMs: number,
): number {
  if (!serverNowIso || !Number.isFinite(clientNowMs)) return 0;
  const serverNowMs = Date.parse(serverNowIso);
  if (!Number.isFinite(serverNowMs)) return 0;
  const updatedAtValid = snapshotUpdatedAtMs != null
    && Number.isFinite(snapshotUpdatedAtMs) && snapshotUpdatedAtMs > 0;
  const clientReceivedAtMs = updatedAtValid ? snapshotUpdatedAtMs : serverNowMs;
  // When the client's clock and server clock do not agree, measure elapsed
  // time from the cached receipt instead of generating imaginary past hours.
  const anchorMs = updatedAtValid && Math.abs(clientReceivedAtMs - serverNowMs) > 10_000
    ? clientReceivedAtMs
    : serverNowMs;
  return Math.max(0, Math.floor(clientNowMs - anchorMs));
}

/** One exact D8 display projection for both cached startup and live ticks.
 * Rate is the aggregate kWh/sec confirmed by the backend, scaled to D8.
 * Never changes server totals, a user's exchange entitlement or ledger. */
export function projectEnergyD8(
  confirmedScaled: bigint,
  aggregateRateScaled: bigint,
  elapsedMs: number,
): bigint {
  const base = confirmedScaled < 0n ? 0n : confirmedScaled;
  if (aggregateRateScaled <= 0n || !Number.isFinite(elapsedMs) || elapsedMs <= 0) return base;
  const wholeMs = Math.floor(elapsedMs);
  if (!Number.isSafeInteger(wholeMs)) return base;
  return base + (aggregateRateScaled * BigInt(wholeMs)) / 1000n;
}
