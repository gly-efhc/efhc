import { z } from "zod";

import { apiRequest } from "../lib/api";
import { fromScaledBigint } from "../lib/format";
import { dbIdSchema } from "../lib/api/db-id";
import { parseGlobalId } from "../types/identity";
import type { PanelsSummary } from "../types/panels";

/** Backend Decimal(D8) can serialize exact values as 0E-8 or 1E-8.
 * Normalize only read-only API values; never use Number/parseFloat for D8.
 * An invalid or inexact extra fraction remains invalid (no silent rounding).
 */
function canonicalSnapshotD8(value: unknown): unknown {
  if (typeof value !== "string" && typeof value !== "number") return value;
  const raw = String(value).trim();
  const match = /^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d{1,3}))?$/.exec(raw);
  if (!match) return value;
  const fraction = match[3] || "";
  const exponent = match[4] ? Number(match[4]) : 0;
  const shift = 8 + exponent - fraction.length;
  // Bounded exponent prevents untrusted payloads from creating huge BigInts.
  if (Math.abs(exponent) > 100 || Math.abs(shift) > 100) return value;
  let units = BigInt(match[2] + fraction);
  if (shift >= 0) units *= 10n ** BigInt(shift);
  else {
    const divisor = 10n ** BigInt(-shift);
    if (units % divisor !== 0n) return value;
    units /= divisor;
  }
  if (match[1] === "-") units = -units;
  return fromScaledBigint(units, 8);
}

const decimalStringSchema = z.preprocess(
  canonicalSnapshotD8,
  z.string().regex(/^-?\d+\.\d{8}$/),
);

const profileSchema = z.object({
  global_id: z.string().transform((value) => parseGlobalId(value)),
  username: z.string().nullable().optional(),
  is_vip: z.boolean(),
  has_activ: z.boolean(),
  main_balance: decimalStringSchema,
  bonus_balance: decimalStringSchema,
  available_kwh: decimalStringSchema,
  total_generated_kwh: decimalStringSchema,
  gen_per_sec_base: decimalStringSchema,
  gen_per_sec_vip: decimalStringSchema,
}).passthrough();

const panelsSummarySchema = z.object({
  active_count: z.number().int().nonnegative(),
  total_generated_by_panels: decimalStringSchema,
  nearest_expire_at: z.string().nullable().optional(),
}).passthrough();

const exchangePreviewSchema = z.object({
  ok: z.boolean(),
  available_kwh: decimalStringSchema,
  max_exchangeable_kwh: decimalStringSchema,
  rate_kwh_to_efhc: decimalStringSchema,
  detail: z.string(),
}).passthrough();

const syncMetaSchema = z.object({
  server_now_iso: z.string(),
  generation_checkpoint_at_iso: z.string().nullable().optional(),
  gen_per_sec_effective: decimalStringSchema,
  next_scheduler_eta_sec: z.number().int().nonnegative(),
  fallback_task_id: dbIdSchema.nullable().optional(),
}).passthrough();

export const syncSnapshotSchema = z.object({
  profile: profileSchema,
  panels: panelsSummarySchema,
  exchange_preview: exchangePreviewSchema,
  meta: syncMetaSchema,
}).passthrough();

export type SyncSnapshot = z.infer<typeof syncSnapshotSchema> & {
  panels: PanelsSummary;
};

export async function fetchSyncSnapshot(signal?: AbortSignal): Promise<SyncSnapshot> {
  const payload = await apiRequest<unknown>(
    "/sync/me?fresh=1",
    "POST",
    {signal},
  );
  return syncSnapshotSchema.parse(payload);
}
