import { z } from "zod";

import { apiRequest } from "../lib/api";
import { dbIdSchema } from "../lib/api/db-id";
import { parseGlobalId } from "../types/identity";
import type { PanelsSummary } from "../types/panels";

const decimalStringSchema = z.preprocess(
  (value) => (typeof value === "number" ? String(value) : value),
  z.string().regex(/^-?\d+(?:\.\d+)?$/),
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
