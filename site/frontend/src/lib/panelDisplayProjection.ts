/** Pure display-only projection for the existing PNL card (exact EFHC D8).
 * Derived from a confirmed panel-list snapshot. No ledger entry, mutation,
 * authorization grant, purchase or offline financial command is created.
 */
import { format8, fromScaledBigint, toScaledBigintDown } from "./format";
import { energyDisplayProjectionWindowMs } from "./energyProjection";

export type PanelGenerationView = {
  generated_kwh: string;
  base_gen_per_sec: string;
  is_active: boolean;
  remaining_seconds?: number | null;
  expires_at?: string | null;
};

export function projectPanelGeneratedD8(
  panel: PanelGenerationView,
  serverNowIso: string | null,
  elapsedClientMs: number,
): string {
  const confirmed = format8(panel.generated_kwh);
  if (!panel.is_active || !serverNowIso || !Number.isFinite(elapsedClientMs) || elapsedClientMs <= 0) {
    return confirmed;
  }
  const expiryLimitMs = energyDisplayProjectionWindowMs(serverNowIso, panel.expires_at ?? null);
  const remainingLimitMs = panel.remaining_seconds == null
    ? Infinity
    : Number.isFinite(panel.remaining_seconds)
      ? Math.max(0, panel.remaining_seconds * 1000)
      : 0;
  const safeMs = Math.floor(Math.max(0, Math.min(elapsedClientMs, expiryLimitMs, remainingLimitMs)));
  if (safeMs <= 0) return confirmed;
  const rate = toScaledBigintDown(panel.base_gen_per_sec, 8);
  if (rate <= 0n) return confirmed;
  const base = toScaledBigintDown(confirmed, 8);
  return fromScaledBigint(base + (rate * BigInt(safeMs)) / 1000n, 8);
}
